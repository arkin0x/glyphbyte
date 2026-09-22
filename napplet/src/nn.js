// Plain-JavaScript inference for the symple classifier. Weights are a flat float16 blob
// (batch-norm already folded into the convolutions) described by a manifest.

export function f16ToF32(u16) {
  const out = new Float32Array(u16.length);
  for (let i = 0; i < u16.length; i++) {
    const h = u16[i], s = (h & 0x8000) ? -1 : 1, e = (h >> 10) & 0x1f, m = h & 0x3ff;
    if (e === 0) out[i] = s * m * Math.pow(2, -24);
    else if (e === 31) out[i] = m ? NaN : s * Infinity;
    else out[i] = s * (1 + m / 1024) * Math.pow(2, e - 15);
  }
  return out;
}

export function loadWeights(manifest, bytes) {
  const u16 = new Uint16Array(bytes.buffer, bytes.byteOffset, bytes.byteLength >> 1);
  const all = f16ToF32(u16);
  const w = {};
  for (const l of manifest.layers) w[l.name] = { data: all.subarray(l.offset, l.offset + l.size), shape: l.shape };
  return { manifest, w };
}

// conv 3x3, padding 1, followed by relu. inp is C*H*W planar, w is O*C*3*3, b is O.
function conv3x3Relu(inp, C, H, W, w, b, O) {
  const out = new Float32Array(O * H * W);
  const HW = H * W;
  for (let o = 0; o < O; o++) {
    const outBase = o * HW;
    out.fill(b[o], outBase, outBase + HW);
    for (let c = 0; c < C; c++) {
      const inBase = c * HW, wBase = (o * C + c) * 9;
      for (let ky = -1; ky <= 1; ky++) {
        for (let kx = -1; kx <= 1; kx++) {
          const wv = w[wBase + (ky + 1) * 3 + (kx + 1)];
          if (wv === 0) continue;
          const y0 = Math.max(0, -ky), y1 = Math.min(H, H - ky);
          const x0 = Math.max(0, -kx), x1 = Math.min(W, W - kx);
          for (let y = y0; y < y1; y++) {
            const orow = outBase + y * W, irow = inBase + (y + ky) * W + kx;
            for (let x = x0; x < x1; x++) out[orow + x] += inp[irow + x] * wv;
          }
        }
      }
    }
    for (let i = outBase; i < outBase + HW; i++) if (out[i] < 0) out[i] = 0;
  }
  return out;
}

function maxPool2(inp, C, H, W) {
  const h = H >> 1, w = W >> 1, out = new Float32Array(C * h * w);
  for (let c = 0; c < C; c++) for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    const i = c * H * W + 2 * y * W + 2 * x;
    out[c * h * w + y * w + x] = Math.max(inp[i], inp[i + 1], inp[i + W], inp[i + W + 1]);
  }
  return out;
}

function softmax(v) {
  let m = -Infinity; for (const x of v) if (x > m) m = x;
  const e = v.map(x => Math.exp(x - m)); const s = e.reduce((a, b) => a + b, 0);
  return e.map(x => x / s);
}

// patch: Float32Array of PATCH*PATCH values in 0..1. Returns {symRot: 64 probs, junk, fill: 2 probs}
export function classify(model, patch, size) {
  const { w, manifest } = model;
  const ch = manifest.channels;
  let x = patch, C = 1, H = size, W = size;
  for (let bi = 0; bi < 4; bi++) {
    const O = ch[bi];
    x = conv3x3Relu(x, C, H, W, w[`conv${bi}_0_w`].data, w[`conv${bi}_0_b`].data, O); C = O;
    x = conv3x3Relu(x, C, H, W, w[`conv${bi}_1_w`].data, w[`conv${bi}_1_b`].data, O);
    x = maxPool2(x, C, H, W); H >>= 1; W >>= 1;
  }
  const feat = new Float32Array(C);
  for (let c = 0; c < C; c++) { let s = 0; for (let i = 0; i < H * W; i++) s += x[c * H * W + i]; feat[c] = s / (H * W); }
  const dense = (name) => { const W_ = w[name + "_w"], b = w[name + "_b"].data, n = W_.shape[0], out = new Array(n);
    for (let o = 0; o < n; o++) { let s = b[o]; for (let c = 0; c < C; c++) s += W_.data[o * C + c] * feat[c]; out[o] = s; } return out; };
  const sym = softmax(dense("sym")), fill = softmax(dense("fill"));
  const junk = sym.length > 64 ? sym[64] : 0;
  const real = sym.slice(0, 64); const rs = real.reduce((a, b) => a + b, 0) || 1;
  return { symRot: real.map(p => p / rs), junk, fill };
}
