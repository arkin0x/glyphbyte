// Same as decode_one but importing the ES modules directly (no VM): the speed a browser JIT sees.
import fs from 'node:fs';
import { readImage, describe } from '../src/pipeline.js';
import { loadWeights } from '../src/nn.js';
const [pgm, weights, manifest] = process.argv.slice(2);
const model = loadWeights(JSON.parse(fs.readFileSync(manifest, 'utf8')), new Uint8Array(fs.readFileSync(weights)));
const b = fs.readFileSync(pgm); let p = 0, tok = []; while (tok.length < 4) { let s = ''; while (b[p] === 0x20 || b[p] === 0x0a) p++; while (b[p] !== 0x20 && b[p] !== 0x0a) s += String.fromCharCode(b[p++]); tok.push(s); } p++;
const W = +tok[1], H = +tok[2], gray = new Uint8Array(b.buffer, b.byteOffset + p, W * H);
for (let i = 0; i < 2; i++) { const t = Date.now(); const r = readImage(gray, W, H, model); console.log(`run ${i + 1}: ${r.best} in ${Date.now() - t} ms, frames ${r.detection.frames.length}, start ${r.detection.startKnown}`); }
