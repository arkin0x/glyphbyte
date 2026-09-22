// Image to candidate byte sequences: port of symple/pipeline.py.
import { detect } from './detect.js';
import { classify } from './nn.js';

export const SYMBOLS = ['house', 'chevron', 'bookmark', 'crown', 'drop', 'tee', 'u', 'mountain', 'arrow', 'heart', 'crescent', 'cloud', 'snowman', 'l', 'trapezoid', 'pacman'];
export function unpack(b) { return { symbol: b >> 4, rotation: (b >> 2) & 3, fill: (b >> 1) & 1, frame: b & 1, name: SYMBOLS[b >> 4] }; }
export function describe(b) { const g = unpack(b); return `${g.name} rotated ${g.rotation * 90} deg, ${g.fill ? 'filled' : 'outline'}, ${g.frame ? 'circle' : 'square'} frame`; }

function byteDistribution(sc, kind, conf) {
  const pf = [0.5, 0.5]; pf[kind] = 0.5 + 0.5 * conf; pf[1 - kind] = 0.5 - 0.5 * conf;
  const dist = new Float64Array(256); let s = 0;
  for (let sr = 0; sr < 64; sr++) for (let fill = 0; fill < 2; fill++) for (let fr = 0; fr < 2; fr++) { const v = sc.symRot[sr] * sc.fill[fill] * pf[fr]; dist[(sr << 2) | (fill << 1) | fr] = v; s += v; }
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
  if (!det.frames.length) return { reads: [], sequences: [], warnings: warnings.concat(['no symbols found']), detection: det };
  const reads = det.frames.map((f, i) => { const sc = classify(model, det.patches[i], 64); const c = candidates(byteDistribution(sc, f.kind, f.conf), forkRatio, maxPer); return { index: i, candidates: c, byte: c[0][0], p: c[0][1], frameConf: f.conf }; });
  let seqs = sequences(reads, maxSeq);
  if (det.baseline && !det.startKnown) {
    const rev = seqs.map(s => ({ bytes: s.bytes.slice().reverse(), hex: s.bytes.slice().reverse().map(b => b.toString(16).padStart(2, '0')).join(''), p: s.p * 0.5 }));
    seqs = seqs.map(s => ({ ...s, p: s.p * 0.5 })).concat(rev).sort((a, b) => b.p - a.p).slice(0, maxSeq);
    warnings.push('reading direction unknown: sequences include the reversed order');
  }
  return { reads, sequences: seqs, best: seqs[0].hex, warnings, detection: det };
}
