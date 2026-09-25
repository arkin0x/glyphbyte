// glyphbyte: one drawn glyph is one byte. Public API of the JavaScript implementation.
export { SYMBOLS, DOT_NAMES, unpack, describe, readImage } from './pipeline.js';
export { detect } from './detect.js';
export { toGray } from './imgops.js';
import { loadWeights } from './nn.js';
export { loadWeights, classify } from './nn.js';
export { drawRow, drawSheet, drawCell, drawDetection } from './render.js';
export { lookup, buildFilters, matchPrefix, fetchProfiles, probeRelay } from './lookup.js';
export { npub, note, nevent, naddr, decodeEntity, bech32Encode, bech32Decode, isAddressable } from './nip19.js';

export function pack(icon, dots) { return (icon << 4) | dots; }

// The bundled small model. In Node this reads the package files; in a browser pass your own
// bytes to loadWeights (for example fetched from your own origin) or use the single-file napplet.
export async function loadBundledModel() {
  const [{ readFile }, { fileURLToPath }] = await Promise.all([import('node:fs/promises'), import('node:url')]);
  const dir = fileURLToPath(new URL('..', import.meta.url));
  const manifest = JSON.parse(await readFile(dir + '/weights.bin.json', 'utf8'));
  return loadWeights(manifest, new Uint8Array(await readFile(dir + '/weights.bin')));
}
export async function loadShapes() {
  const { readFile } = await import('node:fs/promises'); const { fileURLToPath } = await import('node:url');
  return JSON.parse(await readFile(fileURLToPath(new URL('../shapes.json', import.meta.url)), 'utf8'));
}
