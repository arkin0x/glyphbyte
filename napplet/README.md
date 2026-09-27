# glyphbyte

One drawn glyph is one byte. This package is the dependency-free JavaScript implementation
of [GlyphByte](https://glyphbyte.dev): read a hand-drawn row of glyphs from a photo on the
device, render rows to draw from, and resolve the bytes on nostr as event id and pubkey
prefixes. The specification with test vectors is in the repository under `spec/`.

Format v2 is the default from 0.2.0: each glyph is a square frame holding one of 16 upright
icons (the first hex digit) and up to four corner dots (the second: top-left 8, top-right 4,
bottom-right 2, bottom-left 1). Format 1, the first alphabet of rotated, filled pictograms,
still reads: give `readImage` both models and it tells the formats apart per photo
(`result.format`, and every candidate carries its own `format`); `loadShapes(1)` draws v1
rows. Versions 0.1.x read format 1 only.

```js
import { readImage, toGray, loadBundledModels, drawRow, loadShapes, lookup } from 'glyphbyte';

const models = await loadBundledModels();               // {1, 2}; Node. In a browser pass weights to loadWeights()
const gray = toGray(imageData.data, width, height);     // from a canvas
const result = readImage(gray, width, height, models);  // { best, format, sequences, reads, warnings, detection }

drawRow(canvas, await loadShapes(), [0xe8, 0xed, 0x37, 0x98, 0xc6, 0xff]);      // a v2 row to copy from
drawRow(canvas, await loadShapes(1), [0xe8, 0xed, 0x37, 0x98, 0xc6, 0xff]);     // the same bytes in format 1
const hits = await lookup(result.sequences.map(s => s.hex), { relay: 'wss://wheat.oslim.dev' });
```

The same code, bundled into one HTML file, is the GlyphByte napplet (NIP-5D).
License: CC BY-SA 4.0 (code, alphabet, icons and specification).
