# glyphbyte

One drawn glyph is one byte. This package is the dependency-free JavaScript implementation
of [GlyphByte](https://glyphbyte.dev): read a hand-drawn row of glyphs from a photo on the
device, render rows to draw from, and resolve the bytes on nostr as event id and pubkey
prefixes. The specification with test vectors is in the repository under `spec/`.

Format v2 (0.2.0 and later): each glyph is a square frame holding one of 16 upright icons
(the first hex digit) and up to four corner dots (the second: top-left 8, top-right 4,
bottom-right 2, bottom-left 1). Versions 0.1.x read the first alphabet of rotated, filled
pictograms and cannot read v2 rows, nor v2 the old ones.

```js
import { readImage, toGray, loadBundledModel, drawRow, loadShapes, lookup } from 'glyphbyte';

const model = await loadBundledModel();                 // Node; in a browser pass weights to loadWeights()
const gray = toGray(imageData.data, width, height);     // from a canvas
const result = readImage(gray, width, height, model);   // { best, sequences, reads, warnings, detection }

drawRow(canvas, await loadShapes(), [0xe8, 0xed, 0x37, 0x98, 0xc6, 0xff]);   // a row to copy from
const hits = await lookup(result.sequences.map(s => s.hex), { relay: 'wss://wheat.oslim.dev' });
```

The same code, bundled into one HTML file, is the GlyphByte napplet (NIP-5D).
License: CC BY-SA 4.0 (code, alphabet, icons and specification).
