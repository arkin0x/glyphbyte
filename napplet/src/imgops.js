// Image primitives for the symple detector, plain JavaScript, no dependencies.
// Images are row-major typed arrays; binary images are Uint8Array with 1 = ink.

export function toGray(rgba, W, H) {
  const g = new Uint8Array(W * H);
  for (let i = 0, j = 0; i < g.length; i++, j += 4) g[i] = (0.299 * rgba[j] + 0.587 * rgba[j + 1] + 0.114 * rgba[j + 2] + 0.5) | 0;
  return g;
}

export function integral(img, W, H) {
  const S = new Float64Array((W + 1) * (H + 1));
  for (let y = 1; y <= H; y++) {
    let row = 0;
    for (let x = 1; x <= W; x++) { row += img[(y - 1) * W + (x - 1)]; S[y * (W + 1) + x] = S[(y - 1) * (W + 1) + x] + row; }
  }
  return S;
}

function boxSum(S, W, x0, y0, x1, y1) { // inclusive-exclusive box on an integral image
  const w = W + 1;
  return S[y1 * w + x1] - S[y0 * w + x1] - S[y1 * w + x0] + S[y0 * w + x0];
}

// area-averaging downscale (like INTER_AREA), then bilinear for any residual
export function resizeGray(g, W, H, nw, nh) {
  const S = integral(g, W, H), out = new Uint8Array(nw * nh);
  for (let y = 0; y < nh; y++) {
    const y0 = Math.floor(y * H / nh), y1 = Math.max(y0 + 1, Math.floor((y + 1) * H / nh));
    for (let x = 0; x < nw; x++) {
      const x0 = Math.floor(x * W / nw), x1 = Math.max(x0 + 1, Math.floor((x + 1) * W / nw));
      out[y * nw + x] = (boxSum(S, W, x0, y0, x1, y1) / ((x1 - x0) * (y1 - y0)) + 0.5) | 0;
    }
  }
  return out;
}

function boxMean(img, W, H, r) {
  const S = integral(img, W, H), out = new Float32Array(W * H);
  for (let y = 0; y < H; y++) {
    const y0 = Math.max(0, y - r), y1 = Math.min(H, y + r + 1);
    for (let x = 0; x < W; x++) {
      const x0 = Math.max(0, x - r), x1 = Math.min(W, x + r + 1);
      out[y * W + x] = boxSum(S, W, x0, y0, x1, y1) / ((x1 - x0) * (y1 - y0));
    }
  }
  return out;
}

// ink = src <= localMean - C. OpenCV's ADAPTIVE_THRESH_GAUSSIAN_C weights the block window with a
// Gaussian of sigma 0.3*((block-1)*0.5-1)+0.8; three box passes of the matching radius approximate it.
export function adaptiveThreshold(gray, W, H, block, C, invert) {
  const src = invert ? gray.map(v => 255 - v) : gray;
  const sigma = 0.3 * ((block - 1) * 0.5 - 1) + 0.8, r = Math.max(1, Math.round(Math.sqrt(sigma * sigma * 12 / 3 + 1) / 2 - 0.5));
  let m = boxMean(src, W, H, r); m = boxMean(m, W, H, r); m = boxMean(m, W, H, r);
  const out = new Uint8Array(W * H);
  for (let i = 0; i < out.length; i++) out[i] = src[i] <= m[i] - C ? 1 : 0;
  return out;
}

function dilatePlus(b, W, H) {
  const o = new Uint8Array(W * H);
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
    const i = y * W + x;
    if (b[i] || (x > 0 && b[i - 1]) || (x < W - 1 && b[i + 1]) || (y > 0 && b[i - W]) || (y < H - 1 && b[i + W])) o[i] = 1;
  }
  return o;
}
function erodePlus(b, W, H) {
  const o = new Uint8Array(W * H);
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
    const i = y * W + x;
    if (b[i] && (x === 0 || b[i - 1]) && (x === W - 1 || b[i + 1]) && (y === 0 || b[i - W]) && (y === H - 1 || b[i + W])) o[i] = 1;
  }
  return o;
}
export function morphClose3(b, W, H) { return erodePlus(dilatePlus(b, W, H), W, H); }
export function dilate(b, W, H, r) { // square dilation radius r
  const o = new Uint8Array(W * H);
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
    if (!b[y * W + x]) continue;
    for (let dy = -r; dy <= r; dy++) { const yy = y + dy; if (yy < 0 || yy >= H) continue;
      for (let dx = -r; dx <= r; dx++) { const xx = x + dx; if (xx >= 0 && xx < W) o[yy * W + xx] = 1; } }
  }
  return o;
}

// connected components; connectivity 4 or 8. Returns labels (Int32Array, 0 = background) and stats.
export function labelComponents(bin, W, H, conn = 8) {
  const labels = new Int32Array(W * H);
  const parent = [0];
  const find = (a) => { while (parent[a] !== a) { parent[a] = parent[parent[a]]; a = parent[a]; } return a; };
  const union = (a, b) => { a = find(a); b = find(b); if (a !== b) { if (a < b) parent[b] = a; else parent[a] = b; } };
  let next = 1;
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
    const i = y * W + x;
    if (!bin[i]) continue;
    let l = 0;
    const up = y > 0 ? labels[i - W] : 0;
    const left = x > 0 ? labels[i - 1] : 0;
    const ul = conn === 8 && y > 0 && x > 0 ? labels[i - W - 1] : 0;
    const ur = conn === 8 && y > 0 && x < W - 1 ? labels[i - W + 1] : 0;
    if (up) l = up;
    if (left) { if (!l) l = left; else if (left !== l) union(l, left); }
    if (ul) { if (!l) l = ul; else if (ul !== l) union(l, ul); }
    if (ur) { if (!l) l = ur; else if (ur !== l) union(l, ur); }
    if (!l) { l = next++; parent.push(l); }
    labels[i] = l;
  }
  const remap = new Int32Array(next); let n = 0;
  for (let l = 1; l < next; l++) { const r = find(l); if (!remap[r]) remap[r] = ++n; remap[l] = remap[r]; }
  const stats = []; for (let k = 0; k <= n; k++) stats.push({ area: 0, x0: W, y0: H, x1: -1, y1: -1, border: false });
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
    const i = y * W + x; if (!labels[i]) continue;
    const l = remap[labels[i]]; labels[i] = l; const s = stats[l];
    s.area++; if (x < s.x0) s.x0 = x; if (y < s.y0) s.y0 = y; if (x > s.x1) s.x1 = x; if (y > s.y1) s.y1 = y;
    if (x === 0 || y === 0 || x === W - 1 || y === H - 1) s.border = true;
  }
  return { labels, n, stats };
}

export function removeSpecks(ink, W, H, minArea) {
  const { labels, stats } = labelComponents(ink, W, H, 8);
  const out = new Uint8Array(W * H);
  for (let i = 0; i < out.length; i++) if (labels[i] && stats[labels[i]].area >= minArea) out[i] = 1;
  return out;
}

// chamfer distance transform (distance from ink pixels to the nearest background), OpenCV's 3x3 L2 weights
export function distanceTransform(bin, W, H) {
  const a = 0.955, b = 1.3693, INF = 1e9, d = new Float32Array(W * H);
  for (let i = 0; i < d.length; i++) d[i] = bin[i] ? INF : 0;
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
    const i = y * W + x; if (!d[i]) continue; let v = d[i];
    if (x > 0) v = Math.min(v, d[i - 1] + a);
    if (y > 0) { v = Math.min(v, d[i - W] + a); if (x > 0) v = Math.min(v, d[i - W - 1] + b); if (x < W - 1) v = Math.min(v, d[i - W + 1] + b); }
    d[i] = v;
  }
  for (let y = H - 1; y >= 0; y--) for (let x = W - 1; x >= 0; x--) {
    const i = y * W + x; if (!d[i]) continue; let v = d[i];
    if (x < W - 1) v = Math.min(v, d[i + 1] + a);
    if (y < H - 1) { v = Math.min(v, d[i + W] + a); if (x < W - 1) v = Math.min(v, d[i + W + 1] + b); if (x > 0) v = Math.min(v, d[i + W - 1] + b); }
    d[i] = v;
  }
  return d;
}

function gaussKernel(sigma) {
  const k = (Math.round(sigma * 6 + 1) | 1), r = k >> 1, w = new Float64Array(k); let s = 0;
  for (let i = 0; i < k; i++) { w[i] = Math.exp(-((i - r) ** 2) / (2 * sigma * sigma)); s += w[i]; }
  for (let i = 0; i < k; i++) w[i] /= s;
  return w;
}
function reflect101(i, n) { while (i < 0 || i >= n) { if (i < 0) i = -i; if (i >= n) i = 2 * n - 2 - i; } return i; }
export function gaussianBlur(img, W, H, sigma) {
  const w = gaussKernel(sigma), r = w.length >> 1, tmp = new Float32Array(W * H), out = new Float32Array(W * H);
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) { let s = 0; for (let k = -r; k <= r; k++) s += img[y * W + reflect101(x + k, W)] * w[k + r]; tmp[y * W + x] = s; }
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) { let s = 0; for (let k = -r; k <= r; k++) s += tmp[reflect101(y + k, H) * W + x] * w[k + r]; out[y * W + x] = s; }
  return out;
}

// sample src (gray) at dst pixels through the 3x3 matrix M (dst -> src), bilinear, border replicate
export function warp(gray, W, H, M, ow, oh) {
  const out = new Float32Array(ow * oh), offs = [-0.25, 0.25];
  const sample = (px, py) => {
    const den = M[6] * px + M[7] * py + M[8];
    let sx = (M[0] * px + M[1] * py + M[2]) / den, sy = (M[3] * px + M[4] * py + M[5]) / den;
    sx = Math.min(Math.max(sx, 0), W - 1); sy = Math.min(Math.max(sy, 0), H - 1);
    const x0 = Math.floor(sx), y0 = Math.floor(sy), x1 = Math.min(x0 + 1, W - 1), y1 = Math.min(y0 + 1, H - 1), fx = sx - x0, fy = sy - y0;
    return (gray[y0 * W + x0] * (1 - fx) + gray[y0 * W + x1] * fx) * (1 - fy) + (gray[y1 * W + x0] * (1 - fx) + gray[y1 * W + x1] * fx) * fy;
  };
  for (let y = 0; y < oh; y++) for (let x = 0; x < ow; x++) {
    let s = 0; for (const dy of offs) for (const dx of offs) s += sample(x + dx, y + dy);
    out[y * ow + x] = s / 4;
  }
  return out;
}

// same maths as symple.synth.normalize_patch
export function normalizePatch(p, size, lightInk) {
  const bg = gaussianBlur(p, size, size, size / 6), d = new Float32Array(p.length);
  for (let i = 0; i < d.length; i++) d[i] = lightInk ? bg[i] - p[i] : p[i] - bg[i];
  const d2 = new Float32Array(d.length); for (let i = 0; i < d.length; i++) d2[i] = d[i] * d[i];
  const v = gaussianBlur(d2, size, size, size / 4), out = new Float32Array(d.length);
  for (let i = 0; i < d.length; i++) {
    const n = Math.min(3, Math.max(-3, d[i] / (Math.sqrt(v[i]) + 4)));
    out[i] = Math.floor((n + 3) / 6 * 255) / 255;   // uint8 truncation, then /255 as the classifier expects
  }
  return out;
}
