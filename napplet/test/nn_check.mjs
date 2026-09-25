// Compare JS inference with PyTorch on the same patches (python writes the fixtures).
import fs from 'node:fs';
import { loadWeights, classify } from '../src/nn.js';
const dir = process.argv[2];
const manifest = JSON.parse(fs.readFileSync(`${dir}/weights.bin.json`, 'utf8'));
const model = loadWeights(manifest, new Uint8Array(fs.readFileSync(`${dir}/weights.bin`)));
const fx = JSON.parse(fs.readFileSync(`${dir}/fixtures.json`, 'utf8'));
let maxErr = 0, t0 = Date.now();
for (const f of fx) {
  const r = classify(model, Float32Array.from(f.patch), manifest.patch);
  for (let i = 0; i < 16; i++) maxErr = Math.max(maxErr, Math.abs(r.icon[i] - f.icon[i]));
  for (let i = 0; i < 4; i++) maxErr = Math.max(maxErr, Math.abs(r.dots[i] - f.dots[i]));
  maxErr = Math.max(maxErr, Math.abs(r.junk - f.junk));
}
console.log(`patches ${fx.length}  max abs prob diff vs torch ${maxErr.toExponential(2)}  ${((Date.now() - t0) / fx.length).toFixed(0)} ms/patch`);
process.exit(maxErr < 2e-2 ? 0 : 1);
