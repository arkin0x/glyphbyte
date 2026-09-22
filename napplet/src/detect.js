// Port of symple/detect.py: frames, baseline, start dot, rectification. Same numbers, same order.
import { resizeGray, adaptiveThreshold, morphClose3, removeSpecks, labelComponents, distanceTransform, dilate, warp, normalizePatch } from './imgops.js';
import { convexHull, polygonArea, polygonPerimeter, polygonCentroid, pointInPolygon, approxPolyDP, maxInscribedQuad, eigen2, homography, mat3mul, mat3inv } from './geom.js';

export const PATCH = 64, PATCH_MARGIN = 0.12, MAX_SIDE = 1600, JUNK_TOP_K = 24;
export const FRAME_SQUARE = 0, FRAME_CIRCLE = 1;

export function prepare(gray, W, H) {
  const m = Math.max(W, H);
  if (m <= MAX_SIDE) return { gray, W, H, scale: 1 };
  const s = MAX_SIDE / m, nw = Math.round(W * s), nh = Math.round(H * s);
  return { gray: resizeGray(gray, W, H, nw, nh), W: nw, H: nh, scale: s };
}

export function binarize(gray, W, H, light) {
  const side = Math.min(W, H), block = Math.max(31, Math.floor(side / 14) | 1);
  const ink = morphClose3(adaptiveThreshold(gray, W, H, block, 10, light), W, H);
  return removeSpecks(ink, W, H, Math.max(6, (side / 250) ** 2));
}

// rasterize a convex polygon into a w x h mask whose origin is (x0, y0)
function fillConvex(poly, x0, y0, w, h) {
  const mask = new Uint8Array(w * h), n = poly.length;
  for (let y = 0; y < h; y++) {
    const yy = y + y0 + 0.5; let xl = Infinity, xr = -Infinity;
    for (let i = 0; i < n; i++) {
      const [ax, ay] = poly[i], [bx, by] = poly[(i + 1) % n];
      if ((ay <= yy && by > yy) || (by <= yy && ay > yy)) { const x = ax + (yy - ay) * (bx - ax) / (by - ay); if (x < xl) xl = x; if (x > xr) xr = x; }
    }
    if (xl === Infinity) continue;
    const xa = Math.max(0, Math.ceil(xl - x0 - 0.5)), xb = Math.min(w - 1, Math.floor(xr - x0 - 0.5));
    for (let x = xa; x <= xb; x++) mask[y * w + x] = 1;
  }
  return mask;
}

function rayStroke(ink, region, w, h, cx, cy, size, nRays = 16) {
  const limit = Math.max(4, Math.floor(0.35 * size)), slackMax = Math.max(2, Math.floor(0.08 * size)), runs = [];
  for (let k = 0; k < nRays; k++) {
    const a = 2 * Math.PI * k / nRays, dx = Math.cos(a), dy = Math.sin(a);
    let x = cx, y = cy, inside = true, run = 0, slack = 0;
    for (let s = 0; s < Math.floor(0.9 * size) + limit + slackMax; s++) {
      x += dx; y += dy; const xi = Math.round(x), yi = Math.round(y);
      if (xi < 0 || yi < 0 || xi >= w || yi >= h) break;
      if (inside) { if (region[yi * w + xi]) continue; inside = false; }
      if (ink[yi * w + xi]) { run++; if (run > limit) break; }
      else if (run > 0) break;
      else { slack++; if (slack > slackMax) break; }
    }
    runs.push(run);
  }
  const pos = runs.filter(r => r > 0).sort((a, b) => a - b);
  if (pos.length < nRays / 2) return 0;
  return pos.length % 2 ? pos[(pos.length - 1) / 2] : (pos[pos.length / 2 - 1] + pos[pos.length / 2]) / 2;
}

function classifyKind(hull) {
  const { quad, area: qa } = maxInscribedQuad(hull), ha = polygonArea(hull), ratio = qa / Math.max(ha, 1e-6);
  const nv = approxPolyDP(hull, 0.02 * polygonPerimeter(hull)).length;
  const score = (ratio - 0.80) / 0.06 + (5.5 - nv) / 3.0;
  return { kind: score > 0 ? FRAME_SQUARE : FRAME_CIRCLE, conf: Math.min(1, Math.abs(score) / 1.5), quad };
}

// boundary pixels of component k within its bbox
function boundaryPoints(labels, W, H, k, s) {
  const pts = [];
  for (let y = s.y0; y <= s.y1; y++) for (let x = s.x0; x <= s.x1; x++) {
    const i = y * W + x; if (labels[i] !== k) continue;
    if (x === 0 || y === 0 || x === W - 1 || y === H - 1 || labels[i - 1] !== k || labels[i + 1] !== k || labels[i - W] !== k || labels[i + W] !== k) pts.push([x, y]);
  }
  return pts;
}

export function findFrames(ink, W, H) {
  const side = Math.min(W, H), minSize = side / 45, maxSize = side / 1.15, out = [];
  const bg = new Uint8Array(W * H); for (let i = 0; i < bg.length; i++) bg[i] = ink[i] ? 0 : 1;
  const bgLab = labelComponents(bg, W, H, 4), inkLab = labelComponents(ink, W, H, 8);

  const consider = (hull, regionArea, ringOuter) => {
    if (hull.length < 3) return;
    let bx0 = Infinity, by0 = Infinity, bx1 = -Infinity, by1 = -Infinity;
    for (const [x, y] of hull) { if (x < bx0) bx0 = x; if (y < by0) by0 = y; if (x > bx1) bx1 = x; if (y > by1) by1 = y; }
    const bw = bx1 - bx0 + 1, bh = by1 - by0 + 1, big = Math.max(bw, bh);
    if (big < minSize || big > maxSize) return;
    if (big / Math.max(1, Math.min(bw, bh)) > 2.2) return;
    const hullArea = polygonArea(hull);
    if (hullArea <= 0 || regionArea < 20 || regionArea / hullArea < 0.35) return;
    const pad = Math.floor(0.5 * big) + 4, x0 = Math.max(0, Math.floor(bx0) - pad), y0 = Math.max(0, Math.floor(by0) - pad);
    const x1 = Math.min(W, Math.ceil(bx1) + pad), y1 = Math.min(H, Math.ceil(by1) + pad), w = x1 - x0, h = y1 - y0;
    if (w <= 0 || h <= 0) return;
    const mask = fillConvex(hull, x0, y0, w, h);
    let px = 0; for (let i = 0; i < mask.length; i++) px += mask[i];
    if (px < 20) return;
    const inkRoi = new Uint8Array(w * h), inside = new Uint8Array(w * h);
    let inkIn = 0, sx = 0, sy = 0;
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) { const v = ink[(y + y0) * W + x + x0]; inkRoi[y * w + x] = v; if (v && mask[y * w + x]) { inside[y * w + x] = 1; inkIn++; sx += x; sy += y; } }
    const frac = inkIn / px;
    if (frac < 0.015 || frac > 0.75) return;
    let size = Math.sqrt(px);
    const c = polygonCentroid(hull), center = [c[0], c[1]];
    const stroke = rayStroke(inkRoi, mask, w, h, center[0] - x0, center[1] - y0, size);
    if (stroke < 1 || stroke > 0.16 * size) return;
    const { kind, conf, quad } = classifyKind(hull);
    const offC = inkIn ? Math.hypot(sx / inkIn + x0 - center[0], sy / inkIn + y0 - center[1]) / size : 1;
    const cc = labelComponents(inside, w, h, 8);
    let share = 0; if (cc.n) { let m = 0; for (let k = 1; k <= cc.n; k++) m = Math.max(m, cc.stats[k].area); share = m / Math.max(1, inkIn); }
    let q = 1;
    q *= (frac >= 0.04 && frac <= 0.5) ? 1 : 0.5;
    q *= (stroke / size >= 0.02 && stroke / size <= 0.10) ? 1 : 0.5;
    q *= 0.5 + 0.5 * conf;
    q *= offC <= 0.22 ? 1 : 0.5;
    q *= share >= 0.5 ? 1 : (share >= 0.3 ? 0.6 : 0.3);
    if (kind === FRAME_CIRCLE) size = Math.sqrt(px / Math.PI) * 2;
    const fr = { kind, center, size, hull, outer: ringOuter || hull, corners: null, ellipse: null, inkFraction: frac, conf, stroke, quality: q, lightInk: false, junk: 0 };
    if (kind === FRAME_SQUARE && quad) fr.corners = quad.map(p => [center[0] + (p[0] - center[0]) * (1 + 0.5 * stroke / Math.max(size, 1)), center[1] + (p[1] - center[1]) * (1 + 0.5 * stroke / Math.max(size, 1))]);
    // ellipse from the second moments of the hull mask
    let m00 = 0, mx = 0, my = 0;
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) if (mask[y * w + x]) { m00++; mx += x; my += y; }
    mx /= m00; my /= m00;
    let cxx = 0, cxy = 0, cyy = 0;
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) if (mask[y * w + x]) { const dx = x - mx, dy = y - my; cxx += dx * dx; cxy += dx * dy; cyy += dy * dy; }
    cxx /= m00; cxy /= m00; cyy /= m00;
    const e = eigen2(cxx, cxy, cyy);
    fr.ellipse = { cx: mx + x0, cy: my + y0, MA: 4 * Math.sqrt(Math.max(e.evals[0], 1e-6)) + stroke, ma: 4 * Math.sqrt(Math.max(e.evals[1], 1e-6)) + stroke, ang: Math.atan2(e.evecs[0][1], e.evecs[0][0]) * 180 / Math.PI };
    out.push(fr);
  };

  // A) holes: background components not touching the border
  for (let k = 1; k <= bgLab.n; k++) {
    const s = bgLab.stats[k]; if (s.border) continue;
    const big = Math.max(s.x1 - s.x0 + 1, s.y1 - s.y0 + 1); if (big < minSize || big > maxSize) continue;
    consider(convexHull(boundaryPoints(bgLab.labels, W, H, k, s)), s.area, null);
  }
  // B) rings with a pen gap: low-solidity ink components whose hull encloses other ink
  for (let k = 1; k <= inkLab.n; k++) {
    const s = inkLab.stats[k]; const big = Math.max(s.x1 - s.x0 + 1, s.y1 - s.y0 + 1);
    if (big < minSize || big > maxSize) continue;
    const hull = convexHull(boundaryPoints(inkLab.labels, W, H, k, s)); if (hull.length < 3) continue;
    const ha = polygonArea(hull); if (ha <= 0 || s.area / ha > 0.5) continue;
    const c = polygonCentroid(hull), shrink = 1 - 0.06;
    const inner = hull.map(p => [c[0] + (p[0] - c[0]) * shrink, c[1] + (p[1] - c[1]) * shrink]);
    consider(inner, polygonArea(inner), hull);
  }
  // dedupe
  out.sort((a, b) => b.size - a.size);
  const keep = [];
  for (const f of out) {
    let dup = false;
    for (const g of keep) {
      if (Math.hypot(f.center[0] - g.center[0], f.center[1] - g.center[1]) < 0.35 * g.size && f.size < 1.3 * g.size) { dup = true; break; }
      if (f.size > 0.3 * g.size && f.size < 0.8 * g.size && g.quality >= 0.7 * f.quality && pointInPolygon(g.hull, f.center[0], f.center[1])) { dup = true; break; }
    }
    if (!dup) keep.push(f);
  }
  return keep;
}

export function filterRow(frames) {
  const warnings = [], n = frames.length;
  if (n <= 1) return { frames, warnings };
  const pts = frames.map(f => f.center), sizes = frames.map(f => f.size), quality = frames.map(f => f.quality);
  let best = [], bestQ = -1;
  for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) {
    const sRef = (sizes[i] + sizes[j]) / 2, r = sizes[i] / sizes[j];
    if (r < 0.6 || r > 1.67) continue;
    let dx = pts[j][0] - pts[i][0], dy = pts[j][1] - pts[i][1]; const L = Math.hypot(dx, dy);
    if (L < 0.8 * sRef) continue;
    dx /= L; dy /= L; const nx = -dy, ny = dx;
    let ok = [];
    for (let k = 0; k < n; k++) { const off = Math.abs((pts[k][0] - pts[i][0]) * nx + (pts[k][1] - pts[i][1]) * ny); const sr = sizes[k] / sRef; if (off <= 0.45 * sRef && sr >= 0.4 && sr <= 2.5) ok.push(k); }
    const t = k => (pts[k][0] - pts[i][0]) * dx + (pts[k][1] - pts[i][1]) * dy;
    ok.sort((a, b) => t(a) - t(b));
    if (ok.length >= 3) { // smooth size trend
      const ts = ok.map(t), sz = ok.map(k => sizes[k]), mT = ts.reduce((a, b) => a + b, 0) / ts.length, mS = sz.reduce((a, b) => a + b, 0) / sz.length;
      let num = 0, den = 0; for (let k = 0; k < ts.length; k++) { num += (ts[k] - mT) * (sz[k] - mS); den += (ts[k] - mT) ** 2; }
      const slope = den > 1e-9 ? num / den : 0, icpt = mS - slope * mT;
      ok = ok.filter((k, idx) => { const tr = slope * ts[idx] + icpt, a = sz[idx] / Math.max(tr, 1e-6); return a >= 0.65 && a <= 1.5; });
    }
    const spaced = [];
    for (const k of ok) if (!spaced.length || t(k) - t(spaced[spaced.length - 1]) >= 0.8 * Math.min(sizes[k], sizes[spaced[spaced.length - 1]])) spaced.push(k);
    const q = spaced.reduce((a, k) => a + quality[k], 0);
    if (q > bestQ + 1e-9) { bestQ = q; best = spaced; }
  }
  if (best.length < 2) { let bi = 0; for (let k = 1; k < n; k++) if (quality[k] * (1 + 0.001 * sizes[k]) > quality[bi] * (1 + 0.001 * sizes[bi])) bi = k; best = [bi]; }
  if (best.length < n) warnings.push(`dropped ${n - best.length} frame(s) that were not on the row`);
  return { frames: best.map(k => frames[k]), warnings };
}

function rowAxis(frames) {
  if (frames.length < 2) return [1, 0];
  const mx = frames.reduce((s, f) => s + f.center[0], 0) / frames.length, my = frames.reduce((s, f) => s + f.center[1], 0) / frames.length;
  let a = 0, b = 0, d = 0; for (const f of frames) { const dx = f.center[0] - mx, dy = f.center[1] - my; a += dx * dx; b += dx * dy; d += dy * dy; }
  return eigen2(a, b, d).evecs[0];
}
function sampleLine(inkD, W, H, p0, d, t0, t1) {
  const ts = [], hit = [];
  for (let t = t0; t < t1; t += 1) { const x = Math.round(p0[0] + t * d[0]), y = Math.round(p0[1] + t * d[1]); ts.push(t); hit.push(x >= 0 && y >= 0 && x < W && y < H && inkD[y * W + x] > 0); }
  return { ts, hit };
}
function refineLineUnused(ink, inkD, W, H, p0, d, nrm, med, tLo, tHi) {
  let { ts, hit } = sampleLine(inkD, W, H, p0, d, tLo, tHi);
  const band = Math.max(2, Math.floor(0.06 * med)), pts = [];
  for (let i = 0; i < ts.length; i++) { if (!hit[i]) continue; const cx = p0[0] + d[0] * ts[i], cy = p0[1] + d[1] * ts[i];
    for (let o = -band; o <= band; o++) { const x = Math.round(cx + nrm[0] * o), y = Math.round(cy + nrm[1] * o); if (x >= 0 && y >= 0 && x < W && y < H && ink[y * W + x]) pts.push([x, y]); } }
  if (pts.length >= 10) {
    const mx = pts.reduce((s, p) => s + p[0], 0) / pts.length, my = pts.reduce((s, p) => s + p[1], 0) / pts.length;
    let a = 0, b = 0, c = 0; for (const p of pts) { const dx = p[0] - mx, dy = p[1] - my; a += dx * dx; b += dx * dy; c += dy * dy; }
    const n1 = pts.length - 1; let d2 = eigen2(a / n1, b / n1, c / n1).evecs[0];
    if (d2[0] * d[0] + d2[1] * d[1] < 0) d2 = [-d2[0], -d2[1]];
    d = d2; p0 = [mx, my]; nrm = [-d[1], d[0]];
  }
  ({ ts, hit } = sampleLine(inkD, W, H, p0, d, tLo - med, tHi + med));
  const idx = []; for (let i = 0; i < hit.length; i++) if (hit[i]) idx.push(i);
  if (!idx.length) return null;
  const gap = 0.5 * med, runs = []; let start = idx[0];
  for (let k = 0; k + 1 < idx.length; k++) { if (ts[idx[k + 1]] - ts[idx[k]] > gap) { runs.push([start, idx[k]]); start = idx[k + 1]; } }
  runs.push([start, idx[idx.length - 1]]);
  let bestR = runs[0]; for (const r of runs) if (ts[r[1]] - ts[r[0]] > ts[bestR[1]] - ts[bestR[0]]) bestR = r;
  const pa = [p0[0] + d[0] * ts[bestR[0]], p0[1] + d[1] * ts[bestR[0]]], pb = [p0[0] + d[0] * ts[bestR[1]], p0[1] + d[1] * ts[bestR[1]]];
  if (Math.hypot(pb[0] - pa[0], pb[1] - pa[1]) < 1.2 * med) return null;
  return { pa, pb, d, nrm };
}
function fillSmallHoles(ink, W, H, maxArea) {
  const bg = new Uint8Array(W * H); for (let i = 0; i < bg.length; i++) bg[i] = ink[i] ? 0 : 1;
  const lab = labelComponents(bg, W, H, 4), out = ink.slice();
  for (let i = 0; i < out.length; i++) { const l = lab.labels[i]; if (l && !lab.stats[l].border && lab.stats[l].area < maxArea) out[i] = 1; }
  return out;
}
function sampleBand(ink, W, H, p0, d, nrm, t0, t1, tol) {
  const ts = [], hit = [];
  for (let t = t0; t < t1; t += 1) {
    const cx = p0[0] + d[0] * t, cy = p0[1] + d[1] * t; let h = false;
    for (let o = -tol; o <= tol && !h; o++) { const x = Math.round(cx + nrm[0] * o), y = Math.round(cy + nrm[1] * o); if (x >= 0 && y >= 0 && x < W && y < H && ink[y * W + x]) h = true; }
    ts.push(t); hit.push(h);
  }
  return { ts, hit };
}
function refineLine2(ink, inkD, inkLines, W, H, p0, d, nrm, med, tLo, tHi) {
  let { ts, hit } = sampleLine(inkD, W, H, p0, d, tLo, tHi);
  const band = Math.max(3, Math.floor(0.12 * med)), pts = [];
  for (let i = 0; i < ts.length; i++) { if (!hit[i]) continue; const cx = p0[0] + d[0] * ts[i], cy = p0[1] + d[1] * ts[i];
    for (let o = -band; o <= band; o++) { const x = Math.round(cx + nrm[0] * o), y = Math.round(cy + nrm[1] * o); if (x >= 0 && y >= 0 && x < W && y < H && ink[y * W + x]) pts.push([x, y]); } }
  if (pts.length >= 10) {
    const mx = pts.reduce((s, p) => s + p[0], 0) / pts.length, my = pts.reduce((s, p) => s + p[1], 0) / pts.length;
    let a = 0, b = 0, c = 0; for (const p of pts) { const dx = p[0] - mx, dy = p[1] - my; a += dx * dx; b += dx * dy; c += dy * dy; }
    const n1 = pts.length - 1; let d2 = eigen2(a / n1, b / n1, c / n1).evecs[0];
    if (d2[0] * d[0] + d2[1] * d[1] < 0) d2 = [-d2[0], -d2[1]];
    d = d2; p0 = [mx, my]; nrm = [-d[1], d[0]];
  }
  ({ ts, hit } = sampleBand(inkLines, W, H, p0, d, nrm, tLo - med, tHi + med, Math.max(3, Math.floor(0.1 * med))));
  const idx = []; for (let i = 0; i < hit.length; i++) if (hit[i]) idx.push(i);
  if (!idx.length) return null;
  const gap = 0.5 * med, runs = []; let start = idx[0];
  for (let k = 0; k + 1 < idx.length; k++) { if (ts[idx[k + 1]] - ts[idx[k]] > gap) { runs.push([start, idx[k]]); start = idx[k + 1]; } }
  runs.push([start, idx[idx.length - 1]]);
  let bestR = runs[0]; for (const r of runs) if (ts[r[1]] - ts[r[0]] > ts[bestR[1]] - ts[bestR[0]]) bestR = r;
  const pa = [p0[0] + d[0] * ts[bestR[0]], p0[1] + d[1] * ts[bestR[0]]], pb = [p0[0] + d[0] * ts[bestR[1]], p0[1] + d[1] * ts[bestR[1]]];
  if (Math.hypot(pb[0] - pa[0], pb[1] - pa[1]) < 1.2 * med) return null;
  return { pa, pb, d, nrm };
}
function dotEvidence(ink0, W, H, pa, pb, med) {
  const ink = fillSmallHoles(ink0, W, H, (0.35 * med) ** 2), dist = distanceTransform(ink, W, H);
  const thick = (p, radius) => { const x = Math.round(p[0]), y = Math.round(p[1]), r = Math.floor(radius); let m = 0;
    for (let yy = Math.max(0, y - r); yy <= Math.min(H - 1, y + r); yy++) for (let xx = Math.max(0, x - r); xx <= Math.min(W - 1, x + r); xx++) if (dist[yy * W + xx] > m) m = dist[yy * W + xx]; return m; };
  const roundness = (p, radius) => { const x = Math.round(p[0]), y = Math.round(p[1]), r = Math.floor(radius); let m = 0, cx = x, cy = y;
    for (let yy = Math.max(0, y - r); yy <= Math.min(H - 1, y + r); yy++) for (let xx = Math.max(0, x - r); xx <= Math.min(W - 1, x + r); xx++) if (dist[yy * W + xx] > m) { m = dist[yy * W + xx]; cx = xx; cy = yy; }
    if (m <= 0) return 9; const k = Math.floor(1.6 * m) + 1; let s = 0;
    for (let yy = Math.max(0, cy - k); yy <= Math.min(H - 1, cy + k); yy++) for (let xx = Math.max(0, cx - k); xx <= Math.min(W - 1, cx + k); xx++) s += ink[yy * W + xx];
    return s / Math.max(1, Math.PI * m * m); };
  const mids = []; for (let i = 0; i < 9; i++) { const t = 0.25 + 0.5 * i / 8; mids.push(thick([pa[0] + (pb[0] - pa[0]) * t, pa[1] + (pb[1] - pa[1]) * t], Math.max(2, 0.04 * med))); }
  mids.sort((a, b) => a - b); const lineHalf = Math.max(1, mids[4]);
  const L = Math.max(1e-6, Math.hypot(pb[0] - pa[0], pb[1] - pa[1])), u = [(pb[0] - pa[0]) / L, (pb[1] - pa[1]) / L];
  const endScan = (p, dir) => { let best = 0, bp = p; const step = Math.max(1, 0.05 * med);
    for (let t = -0.15 * med; t < 0.4 * med; t += step) { const q = [p[0] + dir[0] * t, p[1] + dir[1] * t], v = thick(q, Math.max(2, 0.12 * med)); if (v > best) { best = v; bp = q; } }
    return [best, bp]; };
  const [ta, qa] = endScan(pa, u), [tb, qb] = endScan(pb, [-u[0], -u[1]]);
  const ra = ta / lineHalf, rb = tb / lineHalf, hi = Math.max(ra, rb), lo = Math.min(ra, rb);
  const rd = roundness(ra > rb ? qa : qb, 0.12 * med);
  if (hi >= 1.8 && lo <= 1.6 && hi >= 1.5 * lo && rd <= 3.5) return { start: ra > rb ? 0 : 1, strength: hi };
  return { start: null, strength: hi };
}

export function findBaseline(ink, W, H, frames) {
  if (!frames.length) return null;
  const sizes = frames.map(f => f.size).sort((a, b) => a - b), med = sizes.length % 2 ? sizes[(sizes.length - 1) / 2] : (sizes[sizes.length / 2 - 1] + sizes[sizes.length / 2]) / 2;
  const m = [frames.reduce((s, f) => s + f.center[0], 0) / frames.length, frames.reduce((s, f) => s + f.center[1], 0) / frames.length];
  let d = rowAxis(frames), nrm = [-d[1], d[0]];
  const along = frames.map(f => (f.center[0] - m[0]) * d[0] + (f.center[1] - m[1]) * d[1]).sort((a, b) => a - b);
  // frames' ink masked out: their edges cannot pose as a baseline, and the underline is scored along the whole row
  const frameMask = new Uint8Array(W * H);
  for (const f of frames) { const mk = fillConvexFull(f.hull, W, H); for (let i = 0; i < mk.length; i++) if (mk[i]) frameMask[i] = 1; }
  const strokes = frames.map(f => f.stroke).sort((a, b) => a - b), kd = Math.max(1, Math.floor((2 * strokes[strokes.length >> 1] + 4) / 2));
  const fm = dilate(frameMask, W, H, kd);
  const inkLines = new Uint8Array(W * H); for (let i = 0; i < inkLines.length; i++) inkLines[i] = ink[i] && !fm[i] ? 1 : 0;
  const tLo = along[0] - 0.6 * med, tHi = along[along.length - 1] + 0.6 * med;
  const inkD = dilate(inkLines, W, H, 2);
  const offs = [], covs = [], nOff = Math.floor(4.8 * med / 2) + 1;
  for (let k = 0; k < nOff; k++) {
    const off = -2.4 * med + 4.8 * med * k / (nOff - 1); if (Math.abs(off) < 0.5 * med) continue;
    const { ts, hit } = sampleLine(inkD, W, H, [m[0] + nrm[0] * off, m[1] + nrm[1] * off], d, tLo, tHi);
    if (ts.length < 4) continue;
    offs.push(off); covs.push(hit.filter(Boolean).length / ts.length);
  }
  if (!offs.length) return null;
  const cands = [];
  for (let i = 0; i < offs.length; i++) {
    if (covs[i] < 0.3) continue;
    let mx = 0; for (let j = Math.max(0, i - 3); j < Math.min(offs.length, i + 4); j++) mx = Math.max(mx, covs[j]);
    if (covs[i] >= mx) { if (cands.length && Math.abs(offs[i] - cands[cands.length - 1][0]) < 0.2 * med) { if (covs[i] > cands[cands.length - 1][1]) cands[cands.length - 1] = [offs[i], covs[i]]; continue; } cands.push([offs[i], covs[i]]); }
  }
  if (!cands.length) return null;
  const scored = [];
  for (const [off, cov] of cands) {
    const r = refineLine2(ink, inkD, inkLines, W, H, [m[0] + nrm[0] * off, m[1] + nrm[1] * off], d, nrm, med, tLo, tHi); if (!r) continue;
    const { start } = dotEvidence(inkLines, W, H, r.pa, r.pb, med);
    const near = Math.abs(off) / med >= 0.5 && Math.abs(off) / med <= 1.5;
    scored.push({ key: [near ? 1 : 0, start !== null ? 1 : 0, -Math.round(Math.abs(off) / med * 10) / 10, cov], off, cov, ...r, start });
  }
  if (!scored.length) return null;
  scored.sort((a, b) => { for (let i = 0; i < 4; i++) if (a.key[i] !== b.key[i]) return b.key[i] - a.key[i]; return 0; });
  let { pa, pb, d: dd, nrm: nn, start } = scored[0];
  let sideSum = 0; for (const f of frames) sideSum += (f.center[0] - pa[0]) * nn[0] + (f.center[1] - pa[1]) * nn[1];
  const side = Math.sign(sideSum / frames.length) || 1, up = [nn[0] * side, nn[1] * side];
  if (start === 0) return { pStart: pa, pEnd: pb, startKnown: true, up };
  if (start === 1) return { pStart: pb, pEnd: pa, startKnown: true, up };
  if (dd[0] < 0 || (dd[0] === 0 && dd[1] < 0)) [pa, pb] = [pb, pa];
  return { pStart: pa, pEnd: pb, startKnown: false, up };
}

function fillConvexFull(poly, W, H) {
  const mask = new Uint8Array(W * H), n = poly.length;
  let y0 = Infinity, y1 = -Infinity; for (const p of poly) { if (p[1] < y0) y0 = p[1]; if (p[1] > y1) y1 = p[1]; }
  for (let y = Math.max(0, Math.floor(y0)); y <= Math.min(H - 1, Math.ceil(y1)); y++) {
    const yy = y + 0.5; let xl = Infinity, xr = -Infinity;
    for (let i = 0; i < n; i++) { const [ax, ay] = poly[i], [bx, by] = poly[(i + 1) % n]; if ((ay <= yy && by > yy) || (by <= yy && ay > yy)) { const x = ax + (yy - ay) * (bx - ax) / (by - ay); if (x < xl) xl = x; if (x > xr) xr = x; } }
    if (xl === Infinity) continue;
    for (let x = Math.max(0, Math.ceil(xl - 0.5)); x <= Math.min(W - 1, Math.floor(xr - 0.5)); x++) mask[y * W + x] = 1;
  }
  return mask;
}

function targetQuad(size = PATCH, margin = PATCH_MARGIN) { const m = size * margin; return [[m, m], [size - m, m], [size - m, size - m], [m, size - m]]; }
function orderCorners(corners, center, d, up) {
  const u = corners.map(c => (c[0] - center[0]) * d[0] + (c[1] - center[1]) * d[1]), v = corners.map(c => (c[0] - center[0]) * up[0] + (c[1] - center[1]) * up[1]);
  const scores = corners.map((c, i) => [-u[i] + v[i], u[i] + v[i], u[i] - v[i], -u[i] - v[i]]);
  const order = [], taken = new Set();
  for (let k = 0; k < 4; k++) { let bi = -1; for (let i = 0; i < 4; i++) if (!taken.has(i) && (bi < 0 || scores[i][k] > scores[bi][k])) bi = i; order.push(bi); taken.add(bi); }
  return order.map(i => corners[i]);
}
function rot3(t) { return Float64Array.from([Math.cos(t), -Math.sin(t), 0, Math.sin(t), Math.cos(t), 0, 0, 0, 1]); }
function circleMatrix(e, d, size = PATCH) {
  const a = e.ang * Math.PI / 180, T = Float64Array.from([1, 0, -e.cx, 0, 1, -e.cy, 0, 0, 1]), S = Float64Array.from([2 / Math.max(e.MA, 1e-6), 0, 0, 0, 2 / Math.max(e.ma, 1e-6), 0, 0, 0, 1]);
  let N = mat3mul(S, mat3mul(rot3(-a), T));
  const ddx = N[0] * d[0] + N[1] * d[1], ddy = N[3] * d[0] + N[4] * d[1], th = Math.atan2(ddy, ddx);
  N = mat3mul(rot3(-th), N);
  const P = homography([[-1, -1], [1, -1], [1, 1], [-1, 1]], targetQuad(size));
  return mat3mul(P, N);
}
export function rectifyFrame(gray, W, H, f, d, up, lightInk) {
  let patch;
  if (f.kind === FRAME_SQUARE && f.corners) {
    const src = orderCorners(f.corners, f.center, d, up), M = homography(targetQuad(), src);   // dst -> src
    patch = warp(gray, W, H, M, PATCH, PATCH);
  } else if (f.ellipse) {
    const M = circleMatrix(f.ellipse, d);
    patch = warp(gray, W, H, mat3inv(M), PATCH, PATCH);
    const uu = [M[0] * up[0] + M[1] * up[1], M[3] * up[0] + M[4] * up[1]];
    if (uu[1] > 0) { const fl = new Float32Array(PATCH * PATCH); for (let y = 0; y < PATCH; y++) fl.set(patch.subarray((PATCH - 1 - y) * PATCH, (PATCH - y) * PATCH), y * PATCH); patch = fl; }
  } else {
    const h = f.size / 2, c = f.center, corners = [[c[0] - h, c[1] - h], [c[0] + h, c[1] - h], [c[0] + h, c[1] + h], [c[0] - h, c[1] + h]];
    patch = warp(gray, W, H, homography(targetQuad(), orderCorners(corners, c, d, up)), PATCH, PATCH);
  }
  return normalizePatch(patch, PATCH, lightInk);
}

export function detect(grayIn, Win, Hin, junkFn = null) {
  const { gray, W, H, scale } = prepare(grayIn, Win, Hin);
  const inks = {}; let pool = [];
  for (const light of [false, true]) {
    const ink = binarize(gray, W, H, light); inks[light] = ink;
    let cov = 0; for (let i = 0; i < ink.length; i++) cov += ink[i]; cov /= ink.length;
    const penalty = 1 - Math.min(0.9, 3 * Math.max(0, cov - 0.2));
    for (const f of findFrames(ink, W, H)) { f.lightInk = light; f.quality *= penalty; pool.push(f); }
  }
  pool.sort((a, b) => b.quality - a.quality);
  let merged = [];
  for (const f of pool) { if (merged.some(g => Math.hypot(f.center[0] - g.center[0], f.center[1] - g.center[1]) < 0.35 * g.size && f.size / g.size > 0.6 && f.size / g.size < 1.6)) continue; merged.push(f); }
  if (junkFn && merged.length) {
    // the network is the expensive part: ask it only about the best-looking candidates
    const top = merged.slice(0, JUNK_TOP_K);
    const pj = junkFn(top.map(f => rectifyFrame(gray, W, H, f, [1, 0], [0, -1], f.lightInk)));
    top.forEach((f, i) => { f.junk = pj[i]; f.quality *= Math.max(0.05, 1 - pj[i]); });
    merged = top.filter(f => f.junk < 0.9);
  }
  let { frames, warnings } = filterRow(merged);
  const votes = frames.reduce((s, f) => s + (f.lightInk ? 1 : -1), 0), lightInk = votes > 0, ink = inks[lightInk];
  let up = [0, -1], d = [1, 0], baseline = null, startKnown = false;
  const bl = findBaseline(ink, W, H, frames);
  if (bl) {
    startKnown = bl.startKnown; up = bl.up;
    const L = Math.hypot(bl.pEnd[0] - bl.pStart[0], bl.pEnd[1] - bl.pStart[1]) || 1e-6;
    d = [(bl.pEnd[0] - bl.pStart[0]) / L, (bl.pEnd[1] - bl.pStart[1]) / L]; baseline = [bl.pStart, bl.pEnd];
    if (!startKnown) warnings.push('baseline found but no start dot: reading left to right');
  } else warnings.push('no baseline: assuming the photo is upright and reads left to right');
  if (frames.length) {
    if (bl) {
      const sizes = frames.map(f => f.size).sort((a, b) => a - b), med = sizes[sizes.length >> 1];
      const length = Math.hypot(baseline[1][0] - baseline[0][0], baseline[1][1] - baseline[0][1]);
      const proj = frames.map(f => (f.center[0] - baseline[0][0]) * d[0] + (f.center[1] - baseline[0][1]) * d[1]);
      const span = frames.length > 1 ? Math.max(...proj) - Math.min(...proj) : 0;
      if (length >= 0.8 * span) { const kept = frames.filter((f, i) => proj[i] >= -0.8 * med && proj[i] <= length + 0.8 * med); if (kept.length && kept.length < frames.length) { warnings.push(`dropped ${frames.length - kept.length} frame(s) beyond the baseline`); frames = kept; } }
      frames.sort((a, b) => ((a.center[0] - baseline[0][0]) * d[0] + (a.center[1] - baseline[0][1]) * d[1]) - ((b.center[0] - baseline[0][0]) * d[0] + (b.center[1] - baseline[0][1]) * d[1]));
    } else frames.sort((a, b) => a.center[0] - b.center[0]);
  }
  const patches = frames.map(f => rectifyFrame(gray, W, H, f, d, up, lightInk));
  return { frames, baseline, startKnown, up, direction: d, lightInk, scale, W, H, warnings, patches };
}
