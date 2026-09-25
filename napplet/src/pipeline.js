// Image to candidate byte sequences: port of glyphbyte/pipeline.py.
import { detect, rectifyFrame } from './detect.js';
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

// how much more likely (nats, summed over the row) a turned reading must be before the glyphs
// overrule the underline; below this both readings are kept as candidates. Same as pipeline.py.
const ORIENT_MARGIN = 2.0;

// true [up, d] when glyphs cut with (up, d) look turned k quarter turns counter-clockwise
function turn(up, d, k) { for (let i = 0; i < ((k % 4) + 4) % 4; i++) [up, d] = [[-d[0], -d[1]], up]; return [up, d]; }

function reorient(det, k, model) {
  const [up, d] = turn(det.up, det.direction, k);
  const frames = det.frames.slice().sort((a, b) => (a.center[0] * d[0] + a.center[1] * d[1]) - (b.center[0] * d[0] + b.center[1] * d[1]));
  const patches = frames.map(f => rectifyFrame(det.gray, det.W, det.H, f, d, up, det.lightInk));
  return { frames, patches, scores: patches.map(p => classify(model, p, 64)), up, d };
}

function readsOf(frames, scores, forkRatio, maxPer) {
  return frames.map((f, i) => { const c = candidates(byteDistribution(scores[i]), forkRatio, maxPer); return { index: i, candidates: c, byte: c[0][0], p: c[0][1], frameConf: f.conf }; });
}

export function readImage(gray, W, H, model, opts = {}) {
  const maxSeq = opts.maxSequences || 8, forkRatio = opts.forkRatio || 0.2, maxPer = opts.maxPerSymbol || 4;
  const junkFn = patches => patches.map(p => classify(model, p, 64).junk);
  const det = detect(gray, W, H, junkFn);
  const warnings = det.warnings.slice();
  if (!det.frames.length) return { reads: [], sequences: [], warnings: warnings.concat(['no glyphs found']), detection: det };
  let frames = det.frames, scores = det.patches.map(p => classify(model, p, 64));
  // every icon but box, plus and x has a top: the glyphs vote on which way the row is turned
  const turns = det.baseline ? [0, 2] : [0, 1, 2, 3];
  const ll = {}; for (const k of turns) ll[k] = scores.reduce((s, sc) => s + Math.log(Math.max(sc.orient[k], 1e-6)), 0);
  const ranked = turns.slice().sort((a, b) => ll[b] - ll[a]);
  let kBest = ranked[0], turned = null;
  if (kBest !== 0 && ll[kBest] - ll[0] > ORIENT_MARGIN) {
    const r = reorient(det, kBest, model);
    frames = r.frames; scores = r.scores; det.up = r.up; det.direction = r.d; det.frames = r.frames; det.patches = r.patches;
    warnings.push(`the glyphs read turned ${90 * kBest} degrees from the underline's side; turned the row`);
  } else if (kBest !== 0 || ll[ranked[0]] - ll[ranked[1]] < ORIENT_MARGIN) turned = kBest === 0 ? ranked[1] : kBest;
  const reads = readsOf(frames, scores, forkRatio, maxPer);
  let seqs = sequences(reads, maxSeq);
  if (turned !== null && !det.startKnown) {
    const r = reorient(det, turned, model), seq2 = sequences(readsOf(r.frames, r.scores, forkRatio, maxPer), maxSeq);
    const w = 1 / (1 + Math.exp(ll[0] - ll[turned]));
    seqs = seqs.map(s => ({ ...s, p: s.p * (1 - w) })).concat(seq2.map(s => ({ ...s, p: s.p * w }))).sort((a, b) => b.p - a.p).slice(0, maxSeq);
    warnings.push(`not sure which way is up: candidates include the row turned ${90 * turned} degrees`);
  }
  return { reads, sequences: seqs, best: seqs[0].hex, warnings, detection: det };
}
