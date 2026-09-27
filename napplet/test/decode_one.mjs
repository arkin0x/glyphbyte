import fs from 'node:fs'; import vm from 'node:vm';
const [pgm, core, weights, manifest, weightsV1 = new URL('../weights-v1.bin', import.meta.url).pathname, manifestV1 = new URL('../weights-v1.bin.json', import.meta.url).pathname] = process.argv.slice(2);
const ctx = vm.createContext({ console }); vm.runInContext(fs.readFileSync(core, 'utf8'), ctx); const S = ctx.GlyphByte;
const model = { 2: S.loadWeights(JSON.parse(fs.readFileSync(manifest, 'utf8')), new Uint8Array(fs.readFileSync(weights))),
                1: S.loadWeights(JSON.parse(fs.readFileSync(manifestV1, 'utf8')), new Uint8Array(fs.readFileSync(weightsV1))) };
const b = fs.readFileSync(pgm); let p = 0, tok = []; while (tok.length < 4) { let s = ''; while (b[p] === 0x20 || b[p] === 0x0a) p++; while (b[p] !== 0x20 && b[p] !== 0x0a) s += String.fromCharCode(b[p++]); tok.push(s); } p++;
const W = +tok[1], H = +tok[2], gray = new Uint8Array(b.buffer, b.byteOffset + p, W * H);
const t = Date.now(); const r = S.readImage(gray, W, H, model); const ms = Date.now() - t;
console.log('best', r.best, 'format', r.format, `(${ms} ms)`); for (const s of r.sequences) console.log('  ', s.hex, s.p.toFixed(3), 'v' + s.format);
for (const rd of r.reads) console.log(`  [${rd.index}]`, S.describe(rd.byte, r.format), rd.p.toFixed(2), rd.candidates.slice(1).map(([b, p]) => `| ${S.describe(b, r.format)} ${p.toFixed(2)}`).join(' '));
for (const w of r.warnings) console.log('  !', w);
console.log('  frames', r.detection.frames.length, 'baseline', !!r.detection.baseline, 'start', r.detection.startKnown, 'lightInk', r.detection.lightInk);
