# glyphbyte

One drawn glyph is one byte. This package is the dependency-free JavaScript implementation
of [GlyphByte](https://glyphbyte.dev): read a hand-drawn row of glyphs from a photo on the
device, render rows to draw from, and resolve the bytes on nostr as event id and pubkey
prefixes. The specification with test vectors is in the repository under `spec/`.

```js
import { readImage, toGray, loadBundledModel, drawRow, loadShapes, lookup } from 'glyphbyte';

const model = await loadBundledModel();                 // Node; in a browser pass weights to loadWeights()
const gray = toGray(imageData.data, width, height);     // from a canvas
const result = readImage(gray, width, height, model);   // { best, sequences, reads, warnings, detection }

drawRow(canvas, await loadShapes(), [0xe8, 0xed, 0x37, 0x98, 0xc6, 0xff]);   // a row to copy from
const hits = await lookup(result.sequences.map(s => s.hex), { relay: 'wss://wheat.oslim.dev' });
```

The same code, bundled into one HTML file, is the GlyphByte napplet (NIP-5D).
Code MIT. The alphabet, shapes and specification are CC BY-SA 4.0.
