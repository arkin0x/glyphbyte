// Read one colour photo (binary PPM, P6) with the JavaScript reader, both formats, as the app does.
// usage: node napplet/test/decode_color.mjs photo.ppm
import fs from 'node:fs';
import { readImage, loadBundledModels, describe } from '../src/index.js';
import { toGray } from '../src/imgops.js';
const b = fs.readFileSync(process.argv[2]); let p = 0; const tok = [];
while (tok.length < 4) { let s = ''; while (b[p] === 0x20 || b[p] === 0x0a) p++; while (b[p] !== 0x20 && b[p] !== 0x0a) s += String.fromCharCode(b[p++]); tok.push(s); } p++;
const W = +tok[1], H = +tok[2], rgba = new Uint8ClampedArray(W * H * 4);
for (let i = 0; i < W * H; i++) { rgba[4 * i] = b[p + 3 * i]; rgba[4 * i + 1] = b[p + 3 * i + 1]; rgba[4 * i + 2] = b[p + 3 * i + 2]; rgba[4 * i + 3] = 255; }
const models = await loadBundledModels(), t = Date.now();
const r = readImage(toGray(rgba, W, H), W, H, models, { rgba });
console.log('best', r.best, 'format', r.format, 'channel', r.detection.channel, `(${Date.now() - t} ms)`, 'scores', JSON.stringify(r.formatScores));
for (const s of r.sequences.slice(0, 4)) console.log('  ', s.hex, s.p.toFixed(3), 'v' + s.format);
for (const rd of r.reads) console.log(`  [${rd.index}]`, describe(rd.byte, r.format), rd.p.toFixed(2));
for (const w of r.warnings) console.log('  !', w);
