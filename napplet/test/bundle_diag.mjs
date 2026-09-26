import fs from 'node:fs'; import vm from 'node:vm';
const [dir, core, weights, manifest, weightsV1 = new URL('../weights-v1.bin', import.meta.url).pathname, manifestV1 = new URL('../weights-v1.bin.json', import.meta.url).pathname] = process.argv.slice(2);
const ctx = vm.createContext({ console }); vm.runInContext(fs.readFileSync(core, 'utf8'), ctx); const S = ctx.GlyphByte;
const model = { 2: S.loadWeights(JSON.parse(fs.readFileSync(manifest, 'utf8')), new Uint8Array(fs.readFileSync(weights))),
                1: S.loadWeights(JSON.parse(fs.readFileSync(manifestV1, 'utf8')), new Uint8Array(fs.readFileSync(weightsV1))) };
function readPGM(path) { const b = fs.readFileSync(path); let p = 0, tok = []; while (tok.length < 4) { let s = ''; while (b[p] === 0x20 || b[p] === 0x0a) p++; while (b[p] !== 0x20 && b[p] !== 0x0a) s += String.fromCharCode(b[p++]); tok.push(s); } p++; return { W: +tok[1], H: +tok[2], gray: new Uint8Array(b.buffer, b.byteOffset + p, +tok[1] * +tok[2]) }; }
const items = JSON.parse(fs.readFileSync(`${dir}/scenes.json`, 'utf8'));
let countOk = 0, allOk = 0, n = 0, high = 0, low = 0, byteOk = 0, cellsMatched = 0, revOk = 0, fmtOk = 0;
for (const it of items) {
  const { W, H, gray } = readPGM(`${dir}/scene_${String(it.i).padStart(2, '0')}.pgm`);
  const r = S.readImage(gray, W, H, model); const truth = it.truth.map(t => t.byte); if (r.format === (it.format || 2)) fmtOk++;
  const sc = r.detection.scale; for (const f of r.detection.frames) { f.center = [f.center[0] / sc, f.center[1] / sc]; f.size /= sc; }
  // align by position: match each read frame to the nearest truth cell
  for (const rd of r.reads) {
    const f = r.detection.frames[rd.index]; const t = it.truth.find(t => Math.hypot(f.center[0] - t.center[0], f.center[1] - t.center[1]) < 0.35 * t.size);
    if (!t) continue; cellsMatched++;
    if (rd.byte >> 4 === t.byte >> 4) high++; if ((rd.byte & 15) === (t.byte & 15)) low++; if (rd.byte === t.byte) byteOk++;
  }
  if (r.reads.length === truth.length) { countOk++; if (r.best === it.hex) allOk++; else if (r.best === truth.slice().reverse().map(b => b.toString(16).padStart(2, '0')).join('')) revOk++; }
}
console.log(`scenes ${items.length}: frame count right ${countOk}, of which whole sequence right ${allOk}, reversed ${revOk}`);
console.log(`matched cells ${cellsMatched}: high nibble ${(high / cellsMatched).toFixed(3)} low nibble ${(low / cellsMatched).toFixed(3)} whole byte ${(byteOk / cellsMatched).toFixed(3)}; format right ${fmtOk} of ${items.length}`);
