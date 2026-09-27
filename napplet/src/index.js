// glyphbyte: one drawn glyph is one byte. Public API of the JavaScript implementation.
export { SYMBOLS, SYMBOLS_V1, DOT_NAMES, DEFAULT_FORMAT, unpack, describe, turnedV1, readImage } from './pipeline.js';
export { detect } from './detect.js';
export { toGray } from './imgops.js';
import { loadWeights } from './nn.js';
export { loadWeights, classify, modelFormat } from './nn.js';
export { drawRow, drawSheet, drawCell, drawDetection } from './render.js';
export { lookup, buildFilters, matchPrefix, fetchProfiles, probeRelay } from './lookup.js';
export { npub, note, nevent, naddr, decodeEntity, bech32Encode, bech32Decode, isAddressable } from './nip19.js';

export function pack(icon, dots) { return (icon << 4) | dots; }                       // format 2
export function packV1(symbol, rotation, fill, frame) { return (symbol << 4) | (rotation << 2) | (fill << 1) | frame; }

// The bundled small models, {1: format 1, 2: format 2}: pass them to readImage and it reads either
// format. In Node this reads the package files; in a browser pass your own bytes to loadWeights (for
// example fetched from your own origin) or use the single-file napplet.
export async function loadBundledModels() {
  const [{ readFile }, { fileURLToPath }] = await Promise.all([import('node:fs/promises'), import('node:url')]);
  const dir = fileURLToPath(new URL('..', import.meta.url));
  const load = async n => loadWeights(JSON.parse(await readFile(`${dir}/${n}.bin.json`, 'utf8')), new Uint8Array(await readFile(`${dir}/${n}.bin`)));
  return { 1: await load('weights-v1'), 2: await load('weights') };
}
// one format's model (0.1.x API)
export async function loadBundledModel(format = 2) { return (await loadBundledModels())[format]; }
// the shapes drawRow takes: format 2 (default) or 1
export async function loadShapes(format = 2) {
  const { readFile } = await import('node:fs/promises'); const { fileURLToPath } = await import('node:url');
  return JSON.parse(await readFile(fileURLToPath(new URL(format === 1 ? '../shapes-v1.json' : '../shapes.json', import.meta.url)), 'utf8'));
}
