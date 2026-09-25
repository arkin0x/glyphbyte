// Image to candidate byte sequences: port of glyphbyte/pipeline.py.
import { detect } from './detect.js';
import { classify } from './nn.js';

export const SYMBOLS = ['house', 'heart', 'drop', 'moon', 'crown', 'arrow', 'box', 'triangle', 'pie', 'tree', 'plus', 'flag', 'x', 'bolt', 'star', 'fish'];
export const DOT_NAMES = ['top-left', 'top-right', 'bottom-right', 'bottom-left'];   // bit 3, 2, 1, 0
export function unpack(b) { const dots = b & 15; return { icon: b >> 4, dots, name: SYMBOLS[b >> 4], corners: DOT_NAMES.filter((_, i) => dots >> (3 - i) & 1) }; }
export function describe(b) { const g = unpack(b), c = g.corners; return `${g.name}, ` + (c.length ? (c.length > 1 ? 'dots ' : 'dot ') + c.join(', ') : 'no dots'); }

// joint probability over all 256 bytes for one cell: icon times each dot bit
function byteDistribution(sc) {
  const dist = new Float64Array(256); let s = 0;
  for (let n = 0; n < 16; n++) {
    let pd = 1; for (let k = 0; k < 4; k++) pd *= (n >> (3 - k) & 1) ? sc.dots[k] : 1 - sc.dots[k];
    for (let i = 0; i < 16; i++) { const v = sc.icon[i] * pd; dist[(i << 4) | n] = v; s += v; }
  }
  for (let i = 0; i < 256; i++) dist[i] /= s || 1;
  return dist;
}
function candidates(dist, forkRatio, maxPer) {
  const order = Array.from(dist.keys()).sort((a, b) => dist[b] - dist[a]), top = dist[order[0]], out = [[order[0], top]];
  for (let i = 1; i < maxPer; i++) if (dist[order[i]] >= forkRatio * top) out.push([order[i], dist[order[i]]]);
  return out;
}
function sequences(reads, maxSeq) {
  let beam = [[[], 1]];
  for (const r of reads) { const nxt = []; for (const [seq, p] of beam) for (const [b, pb] of r.candidates) nxt.push([seq.concat([b]), p * pb]); nxt.sort((a, b) => b[1] - a[1]); beam = nxt.slice(0, maxSeq); }
  const tot = beam.reduce((s, x) => s + x[1], 0) || 1;
  return beam.map(([seq, p]) => ({ bytes: seq, hex: seq.map(b => b.toString(16).padStart(2, '0')).join(''), p: p / tot }));
}

export function readImage(gray, W, H, model, opts = {}) {
  const maxSeq = opts.maxSequences || 8, forkRatio = opts.forkRatio || 0.2, maxPer = opts.maxPerSymbol || 4;
  const junkFn = patches => patches.map(p => classify(model, p, 64).junk);
  const det = detect(gray, W, H, junkFn);
  const warnings = det.warnings.slice();
  if (!det.frames.length) return { reads: [], sequences: [], warnings: warnings.concat(['no glyphs found']), detection: det };
  const reads = det.frames.map((f, i) => { const sc = classify(model, det.patches[i], 64); const c = candidates(byteDistribution(sc), forkRatio, maxPer); return { index: i, candidates: c, byte: c[0][0], p: c[0][1], frameConf: f.conf }; });
  let seqs = sequences(reads, maxSeq);
  if (det.baseline && !det.startKnown) {
    const rev = seqs.map(s => ({ bytes: s.bytes.slice().reverse(), hex: s.bytes.slice().reverse().map(b => b.toString(16).padStart(2, '0')).join(''), p: s.p * 0.5 }));
    seqs = seqs.map(s => ({ ...s, p: s.p * 0.5 })).concat(rev).sort((a, b) => b.p - a.p).slice(0, maxSeq);
    warnings.push('reading direction unknown: sequences include the reversed order');
  }
  return { reads, sequences: seqs, best: seqs[0].hex, warnings, detection: det };
}
