// Run the bundled core (a classic script) in a bare VM context on the exported scenes: proves
// the single-file bundle works without a DOM, and reports how it decodes.
import fs from 'node:fs'; import vm from 'node:vm';
const [dir, core, weights, manifest, weightsV1 = new URL('../weights-v1.bin', import.meta.url).pathname, manifestV1 = new URL('../weights-v1.bin.json', import.meta.url).pathname] = process.argv.slice(2);
const ctx = vm.createContext({ console }); vm.runInContext(fs.readFileSync(core, 'utf8'), ctx);
const S = ctx.GlyphByte;
const model = { 2: S.loadWeights(JSON.parse(fs.readFileSync(manifest, 'utf8')), new Uint8Array(fs.readFileSync(weights))),
                1: S.loadWeights(JSON.parse(fs.readFileSync(manifestV1, 'utf8')), new Uint8Array(fs.readFileSync(weightsV1))) };
function readPGM(path) { const b = fs.readFileSync(path); let p = 0, tok = []; while (tok.length < 4) { let s = ''; while (b[p] === 0x20 || b[p] === 0x0a) p++; while (b[p] !== 0x20 && b[p] !== 0x0a) s += String.fromCharCode(b[p++]); tok.push(s); } p++; return { W: +tok[1], H: +tok[2], gray: new Uint8Array(b.buffer, b.byteOffset + p, +tok[1] * +tok[2]) }; }
const items = JSON.parse(fs.readFileSync(`${dir}/scenes.json`, 'utf8'));
let exact = 0, inCands = 0, ms = 0;
for (const it of items) {
  const { W, H, gray } = readPGM(`${dir}/scene_${String(it.i).padStart(2, '0')}.pgm`);
  const t = Date.now(); const r = S.readImage(gray, W, H, model); ms += Date.now() - t;
  if (r.best === it.hex) exact++; if (r.sequences.some(s => s.hex === it.hex)) inCands++;
}
console.log(`bundle: ${items.length} scenes, exact ${exact}, truth among candidates ${inCands}, ${(ms / items.length).toFixed(0)} ms/scene`);
