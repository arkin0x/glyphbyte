import fs from 'node:fs';
import { detect } from '../src/detect.js';
const dir = process.argv[2];
const items = JSON.parse(fs.readFileSync(`${dir}/scenes.json`, 'utf8'));
function readPGM(path) { const b = fs.readFileSync(path); let p = 0, tok = []; while (tok.length < 4) { let s = ''; while (b[p] === 0x20 || b[p] === 0x0a) p++; while (b[p] !== 0x20 && b[p] !== 0x0a) s += String.fromCharCode(b[p++]); tok.push(s); } p++; return { W: +tok[1], H: +tok[2], gray: new Uint8Array(b.buffer, b.byteOffset + p, +tok[1] * +tok[2]) }; }
const near = (a, b, tol) => Math.hypot(a[0] - b[0], a[1] - b[1]) < tol;
let cells = 0, jsFound = 0, pyFound = 0, kindOk = 0, kindN = 0, agreeFrames = 0, blJs = 0, blPy = 0, startJs = 0, startPy = 0, dirJs = 0, dirPy = 0, upJs = 0, upPy = 0, ms = 0, extrasJs = 0, extrasPy = 0;
for (const it of items) {
  const { W, H, gray } = readPGM(`${dir}/scene_${String(it.i).padStart(2, '0')}.pgm`);
  const t = Date.now(); const det = detect(gray, W, H); ms += Date.now() - t;
  const sc = det.scale; for (const f of det.frames) { f.center = [f.center[0] / sc, f.center[1] / sc]; f.size /= sc; }
  cells += it.truth.length;
  for (const tr of it.truth) {
    const fj = det.frames.find(f => near(f.center, tr.center, 0.35 * tr.size) && f.size > 0.6 * tr.size && f.size < 1.5 * tr.size);
    const fp = it.py.frames.find(f => near(f.center, tr.center, 0.35 * tr.size) && f.size > 0.6 * tr.size && f.size < 1.5 * tr.size);
    if (fj) { jsFound++; kindN++; if (fj.kind === 0) kindOk++; }   // v2 frames are all squares
    if (fp) pyFound++;
    if (!!fj === !!fp) agreeFrames++;
  }
  extrasJs += det.frames.filter(f => !it.truth.some(tr => near(f.center, tr.center, 0.35 * tr.size))).length;
  extrasPy += it.py.frames.filter(f => !it.truth.some(tr => near(f.center, tr.center, 0.35 * tr.size))).length;
  if (det.baseline) blJs++; if (it.py.baseline) blPy++;
  if (det.startKnown) startJs++; if (it.py.start_known) startPy++;
  if (det.baseline && it.py.baseline) {
    if (det.direction[0] * it.py.direction[0] + det.direction[1] * it.py.direction[1] > 0.95) dirJs++;
    if (det.up[0] * it.py.up[0] + det.up[1] * it.py.up[1] > 0.9) upJs++;
  }
}
console.log(`cells ${cells}: JS found ${jsFound}, Python found ${pyFound}, per-cell agreement ${(agreeFrames / cells).toFixed(3)}; kind acc JS ${(kindOk / Math.max(1, kindN)).toFixed(3)}; extras JS ${extrasJs} Py ${extrasPy}`);
console.log(`baseline JS ${blJs} Py ${blPy}; start known JS ${startJs} Py ${startPy}; among both-found: direction agree ${dirJs}, up agree ${upJs}; ${(ms / items.length).toFixed(0)} ms/scene`);
