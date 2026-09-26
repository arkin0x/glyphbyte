// Image to candidate byte sequences, in whichever format the row was drawn: port of glyphbyte/pipeline.py.
// The row is found once, then read as format 2 (icons and corner dots, the default) and as format 1 (the
// first alphabet of rotated, filled pictograms). The better-explained format wins; when the two are close,
// the other format's readings stay among the candidates, each tagged with its format.
import { detect, rectifyFrame } from './detect.js';
import { classify, modelFormat } from './nn.js';

export const SYMBOLS = ['house', 'heart', 'drop', 'moon', 'crown', 'arrow', 'box', 'triangle', 'pie', 'tree', 'plus', 'flag', 'x', 'bolt', 'star', 'fish'];
export const SYMBOLS_V1 = ['house', 'chevron', 'bookmark', 'crown', 'drop', 'tee', 'u', 'mountain', 'arrow', 'heart', 'crescent', 'cloud', 'snowman', 'l', 'trapezoid', 'pacman'];
export const DOT_NAMES = ['top-left', 'top-right', 'bottom-right', 'bottom-left'];   // bit 3, 2, 1, 0
export const DEFAULT_FORMAT = 2;

export function unpack(b, fmt = DEFAULT_FORMAT) {
  if (fmt === 1) return { fmt: 1, symbol: b >> 4, rotation: (b >> 2) & 3, fill: (b >> 1) & 1, frame: b & 1, name: SYMBOLS_V1[b >> 4] };
  const dots = b & 15; return { fmt: 2, icon: b >> 4, dots, name: SYMBOLS[b >> 4], corners: DOT_NAMES.filter((_, i) => dots >> (3 - i) & 1) };
}
export function describe(b, fmt = DEFAULT_FORMAT) {
  const g = unpack(b, fmt);
  if (fmt === 1) return `${g.name} rotated ${g.rotation * 90} deg, ${g.fill ? 'filled' : 'outline'}, ${g.frame ? 'circle' : 'square'} frame`;
  const c = g.corners; return `${g.name}, ` + (c.length ? (c.length > 1 ? 'dots ' : 'dot ') + c.join(', ') : 'no dots');
}
// the byte a format 1 glyph reads as when the whole row is turned clockwise by quarter turns
export function turnedV1(b, q) { return (b & 0xf3) | ((((b >> 2) & 3) + q) % 4) << 2; }

// how much more likely (nats, summed over the row) a turned reading must be before the glyphs overrule the
// underline; below this both readings are kept. Format choice constants as in pipeline.py.
const ORIENT_MARGIN = 2.0, FORMAT_BIAS = 0.5, FORMAT_FORK = 0.5, RESCUE = 0.3;   // the format ones are per glyph

function distV2(sc) {
  const dist = new Float64Array(256); let s = 0;
  for (let n = 0; n < 16; n++) {
    let pd = 1; for (let k = 0; k < 4; k++) pd *= (n >> (3 - k) & 1) ? sc.dots[k] : 1 - sc.dots[k];
    for (let i = 0; i < 16; i++) { const v = sc.icon[i] * pd; dist[(i << 4) | n] = v; s += v; }
  }
  for (let i = 0; i < 256; i++) dist[i] /= s || 1;
  return dist;
}
function distV1(sc, kind, conf) {
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
const hexOf = seq => seq.map(b => b.toString(16).padStart(2, '0')).join('');
function sequences(reads, maxSeq, fmt) {
  let beam = [[[], 1]];
  for (const r of reads) { const nxt = []; for (const [seq, p] of beam) for (const [b, pb] of r.candidates) nxt.push([seq.concat([b]), p * pb]); nxt.sort((a, b) => b[1] - a[1]); beam = nxt.slice(0, maxSeq); }
  const tot = beam.reduce((s, x) => s + x[1], 0) || 1;
  return beam.map(([seq, p]) => ({ bytes: seq, hex: hexOf(seq), p: p / tot, format: fmt }));
}
const rowLL = dists => dists.reduce((s, d) => s + Math.log(Math.max(Math.max(...d), 1e-12)), 0);
const merge = (a, wa, b, wb, maxSeq) => a.map(s => ({ ...s, p: s.p * wa })).concat(b.map(s => ({ ...s, p: s.p * wb }))).sort((x, y) => y.p - x.p).slice(0, maxSeq);

// true [up, d] when glyphs cut with (up, d) look turned k quarter turns counter-clockwise
function turn(up, d, k) { for (let i = 0; i < ((k % 4) + 4) % 4; i++) [up, d] = [[-d[0], -d[1]], up]; return [up, d]; }

function cut(det, up, d, fmt) {
  const frames = det.frames.slice().sort((a, b) => (a.center[0] * d[0] + a.center[1] * d[1]) - (b.center[0] * d[0] + b.center[1] * d[1]));
  return { frames, patches: frames.map(f => rectifyFrame(det.gray, det.W, det.H, f, d, up, det.lightInk, fmt)) };
}
function readsOf(frames, dists, forkRatio, maxPer, fmt) {
  return frames.map((f, i) => { const c = candidates(dists[i], forkRatio, maxPer); return { index: i, candidates: c, byte: c[0][0], p: c[0][1], frameConf: f.conf, format: fmt }; });
}

function readV2(det, model, o) {
  const warnings = [];
  let { frames, up, direction: d } = det, patches = det.patches.length === frames.length ? det.patches : cut(det, up, d, 2).patches;
  let scores = patches.map(p => classify(model, p, 64));
  // every icon but box, plus and x has a top: the glyphs vote on which way the row is turned
  const turns = det.baseline ? [0, 2] : [0, 1, 2, 3];
  const ll = {}; for (const k of turns) ll[k] = scores.reduce((s, sc) => s + Math.log(Math.max(sc.orient[k], 1e-6)), 0);
  const ranked = turns.slice().sort((a, b) => ll[b] - ll[a]), kBest = ranked[0];
  let turned = null;
  if (kBest !== 0 && ll[kBest] - ll[0] > ORIENT_MARGIN) {
    [up, d] = turn(det.up, det.direction, kBest); ({ frames, patches } = cut(det, up, d, 2)); scores = patches.map(p => classify(model, p, 64));
    warnings.push(`the glyphs read turned ${90 * kBest} degrees from the underline's side; turned the row`);
  } else if (kBest !== 0 || ll[ranked[0]] - ll[ranked[1]] < ORIENT_MARGIN) turned = kBest === 0 ? ranked[1] : kBest;
  const dists = scores.map(distV2), reads = readsOf(frames, dists, o.forkRatio, o.maxPer, 2);
  let seqs = sequences(reads, o.maxSeq, 2);
  if (turned !== null && !det.startKnown) {
    const [u2, d2] = turn(det.up, det.direction, turned), c2 = cut(det, u2, d2, 2);
    const seq2 = sequences(readsOf(c2.frames, c2.patches.map(p => distV2(classify(model, p, 64))), o.forkRatio, o.maxPer, 2), o.maxSeq, 2);
    const w = 1 / (1 + Math.exp(ll[0] - ll[turned]));
    seqs = merge(seqs, 1 - w, seq2, w, o.maxSeq);
    warnings.push(`not sure which way is up: candidates include the row turned ${90 * turned} degrees`);
  }
  return { fmt: 2, reads, sequences: seqs, ll: rowLL(dists), warnings, frames, patches, up, d };
}

function readV1(det, model, o) {
  const warnings = [], { frames, patches } = cut(det, det.up, det.direction, 1);
  const dists = patches.map((p, i) => distV1(classify(model, p, 64), frames[i].kind, frames[i].conf));
  const reads = readsOf(frames, dists, o.forkRatio, o.maxPer, 1);
  let seqs = sequences(reads, o.maxSeq, 1);
  if (!det.startKnown) {
    // v1 pictograms are drawn in every rotation, so they cannot say which way is up: the row turned
    // 180 degrees reads in reverse, every glyph's rotation two quarter turns on
    const rev = seqs.map(s => { const b = s.bytes.slice().reverse().map(x => turnedV1(x, 2)); return { bytes: b, hex: hexOf(b), p: s.p, format: 1 }; });
    seqs = merge(seqs, 0.5, rev, 0.5, o.maxSeq);
    warnings.push('format 1 has no top to read: candidates include the row turned 180 degrees');
  }
  return { fmt: 1, reads, sequences: seqs, ll: rowLL(dists), warnings, frames, patches, up: det.up, d: det.direction };
}

// models: one loaded model (its format only) or {1: model, 2: model}. opts.format: 'auto' (default), 1 or 2.
export function readImage(gray, W, H, models, opts = {}) {
  const o = { maxSeq: opts.maxSequences || 8, forkRatio: opts.forkRatio || 0.2, maxPer: opts.maxPerSymbol || 4 };
  let byFmt = models && models.w ? { [modelFormat(models)]: models } : { ...models };
  if (opts.format && opts.format !== 'auto') byFmt = { [opts.format]: byFmt[opts.format] };
  const fmts = Object.keys(byFmt).map(Number).filter(f => byFmt[f]).sort((a, b) => b - a);
  // junk: format 2 decides; format 1 gets a second look only at what format 2 rejects
  const junkFn = (g, w, h, frames) => {
    const pj = frames.map(f => classify(byFmt[fmts[0]], rectifyFrame(g, w, h, f, [1, 0], [0, -1], f.lightInk, fmts[0]), 64).junk);
    // only a clear glyph of the other format overrules (RESCUE as in pipeline.py)
    for (const fm of fmts.slice(1)) frames.forEach((f, i) => { if (pj[i] > 0.5) { const p = classify(byFmt[fm], rectifyFrame(g, w, h, f, [1, 0], [0, -1], f.lightInk, fm), 64).junk; if (p < RESCUE) pj[i] = Math.min(pj[i], p); } });
    return pj;
  };
  const det = detect(gray, W, H, junkFn);
  const warnings = det.warnings.slice();
  if (!det.frames.length) return { reads: [], sequences: [], format: fmts[0], warnings: warnings.concat(['no glyphs found']), detection: det };
  // format 1 wins only by beating format 2 by FORMAT_BIAS per glyph and scores at most 0, so it is not
  // read when format 2 is above -FORMAT_BIAS per glyph (fmts is sorted 2 before 1)
  const results = {};
  for (const f of fmts) {
    if (f === 1 && results[2] && results[2].ll / Math.max(1, det.frames.length) > -FORMAT_BIAS) continue;
    results[f] = (f === 1 ? readV1 : readV2)(det, byFmt[f], o);
  }
  let chosen, seqs;
  if (!(results[1] && results[2])) { chosen = results[2] || results[1]; seqs = chosen.sequences; }
  else {
    const n = Math.max(1, det.frames.length), margin = (results[1].ll - results[2].ll) / n - FORMAT_BIAS;   // per glyph; > 0 favours format 1
    chosen = margin > 0 ? results[1] : results[2]; const other = margin > 0 ? results[2] : results[1];
    seqs = chosen.sequences;
    if (Math.abs(margin) < FORMAT_FORK) {
      const w = 1 / (1 + Math.exp(Math.abs(margin) * n));
      seqs = merge(chosen.sequences, 1 - w, other.sequences, w, o.maxSeq);
      warnings.push(`the row could be format ${other.fmt}: its readings are among the candidates`);
    }
    if (chosen.fmt === 1) warnings.push('read as format 1, the first glyphbyte alphabet');
  }
  Object.assign(det, { frames: chosen.frames, patches: chosen.patches, up: chosen.up, direction: chosen.d });
  return { reads: chosen.reads, sequences: seqs, best: seqs[0].hex, format: chosen.fmt, warnings: warnings.concat(chosen.warnings), detection: det };
}
