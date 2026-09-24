# glyphbyte

One drawn glyph is one byte. The specification with test vectors is in [`spec/GLYPHBYTE.md`](spec/GLYPHBYTE.md). (Developed under the working name *symple* on 2026-09-22.)

Hand-drawn symbols to bytes, offline. Draw a row of **glyphbyte** symbols on a wall, a
notebook, a sticker or a whiteboard, photograph it, and `glyphbyte decode` returns the
bytes. It was built to carry partial nostr event ids attached to physical places,
where a wrong read costs one extra relay query and nothing else.

```
$ glyphbyte decode photo.jpg
8a3a3a6609eb
$ glyphbyte decode photo.jpg -v
8a3a3a6609eb
  8a3a3a6609eb  p=0.91
  8a3a3a6609e3  p=0.06
  [0] arrow rotated 180 deg, filled, square frame (0.99)
  [5] trapezoid rotated 180 deg, filled, circle frame (0.71)  or trapezoid rotated 0 deg, filled, circle frame (0.22)
```

No network at runtime. Dependencies: numpy, OpenCV, onnxruntime.

## The code: one symbol, one byte

| bits | what | values |
|---|---|---|
| 7..4 | which symbol | 16 symbols, sheet order below |
| 3..2 | rotation | quarter turns clockwise: 0, 90, 180, 270 |
| 1 | fill | 0 outline, 1 filled in |
| 0 | frame | 0 square around the symbol, 1 circle around it |

16 x 4 x 2 x 2 = 256, so every byte has exactly one drawing and every drawing is one byte.

| # | name | how to draw it |
|---|---|---|
| 0 | house | a square with a pointed roof |
| 1 | chevron | a house whose base is cut by a chevron, an upward notch |
| 2 | bookmark | a rectangle with a chevron cut into the bottom |
| 3 | crown | a rectangle with three points on top |
| 4 | drop | a teardrop, point up |
| 5 | tee | the letter T, in block form |
| 6 | u | the letter U, in block form |
| 7 | mountain | a triangle whose apex is split into two peaks |
| 8 | arrow | a chevron head on a shaft, pointing up |
| 9 | heart | a heart |
| 10 | crescent | a thick crescent lying like a bowl, horns up |
| 11 | cloud | a dome with three scallops underneath |
| 12 | snowman | a small circle merged onto a larger circle, small one on top |
| 13 | l | the letter L, in block form |
| 14 | trapezoid | narrow top, wide bottom |
| 15 | pacman | a disc with a wedge bitten out of the top |

Every symbol is distinct from every other symbol in all four rotations, and stays
distinct when filled. `glyphbyte sheet` renders the whole set for printing.

Four symbols from the original 2026-09-22 sheet were retired because they differed from
another symbol only by a small feature that handwriting loses first: **spade** (an
upside-down heart plus a stem), **clover** (a heart plus one bump), **shield** (a cloud
without its scallops when upside down) and **ring dot** (its rotation cue vanishes when
filled). They live in `glyphbyte/data/retired.json`; the sheet is in `assets/`.

## How to write a row

1. Draw the symbols left to right, each inside its frame, roughly the same size,
   with a gap of about a third of a symbol between frames.
2. Underline the whole row with one stroke, and put a **fat dot at the start** of the
   underline, about a quarter of a symbol across. The line tells the reader which way is
   up, the dot tells it where to start. Without them a photo taken sideways has every
   rotation bit wrong, and `glyphbyte` will say so in its warnings.
3. Fill means fill: scribble the whole inside. Outline means a single stroke.

`glyphbyte encode 8a3a3a6609eb --out row.png` renders a row to copy from, and
`--hand 0.7` shows what a sloppy one still looks like.

## Uncertainty is forked, not hidden

When a symbol could be one of two things, the decoder keeps both. The result carries
ranked candidates per symbol and the most probable whole sequences, so a client can
query all of them (cheap on nostr) and show the alternatives to the person holding the
phone. `--fork-ratio` sets how likely an alternative must be, relative to the best
read, to be kept; `--max-sequences` caps the list. If the start dot is missing, the
reversed reading is offered too. There is no checksum by design: for an id prefix of
eight bytes, a wrong candidate simply matches nothing.

## How it works

| stage | method |
|---|---|
| binarize | local threshold at both polarities (dark ink on light, light ink on dark), specks removed |
| frames | interiors of ink rings that hold a compact blob of ink; rings with a pen gap are recovered from their convex hull; a stroke-width check by ray marching rejects paper regions and thick texture |
| square or circle | area of the largest quadrilateral inscribed in the interior's hull over the hull area: 1 for a quadrilateral, 2/pi for an ellipse, in any perspective |
| the row | the set of frames sharing a line and a smooth size trend with the highest total quality, so tiles and windows in the backdrop lose |
| baseline and start | parallel offsets scored by ink coverage in the gaps between frames; each candidate line is refined and tested for a fat end; a line with a dot beats a lined-paper line |
| rectify | squares by homography from their corners, circles by mapping the fitted ellipse to a circle, both rotated so the baseline is horizontal |
| classify | a 4-block CNN (about 0.9M parameters) on 64x64 contrast-normalized patches, two heads: symbol x rotation (64 classes) and fill; polarity-invariant; ONNX on CPU |
| decode | joint probability over the 256 bytes per cell from the two heads and the frame decision, then a beam over cells |

The classifier is trained only on synthetic data rendered from the canonical shapes:
wobble, stroke breathing, pen gaps, scribbled fills, perspective, lighting, shadows,
blur, noise, JPEG, on photographs and procedural surfaces. See `glyphbyte train`.

## Commands

| command | does |
|---|---|
| `glyphbyte decode IMG... [-v] [--json] [--debug out.png]` | read a photo; `--json` gives candidates and warnings; `--debug` writes the detection overlay |
| `glyphbyte encode HEX --out row.png [--hand 0.7]` | render bytes as a row |
| `glyphbyte sheet --out sheet.png` | the reference sheet, all symbols, rotations and fills |
| `glyphbyte synth --out DIR --n 200 --backdrops DIR` | generate photo-like test scenes with ground truth |
| `glyphbyte bench DIR` | decode a synth directory and report accuracy |
| `glyphbyte backdrops --out bench/backdrops` | fetch public-domain photos from picsum.photos for synth |
| `glyphbyte train --backdrops DIR` | retrain the classifier (needs the `train` extra: torch) |

## On device: the napplet

Scanning should cost nothing per photo, so the recognizer also exists as a **napplet**
([NIP-5D](https://github.com/nostr-protocol/nips/pull/2303)): one self-contained
`index.html` that a Nostr shell loads in a sandboxed iframe. No server, no network, no
external scripts: the detector, the network weights and the symbol shapes are all inline,
and everything runs in plain JavaScript on the phone. `napplet/` holds the port:

| file | what |
|---|---|
| `src/imgops.js`, `src/geom.js` | the image and geometry primitives OpenCV provided in Python |
| `src/detect.js` | the detector, same logic and thresholds as `glyphbyte/detect.py` |
| `src/nn.js` | inference for the small classifier (channels 16-32-64-96, batch-norm folded, float16 weights, about 430 KB) |
| `src/pipeline.js`, `src/render.js`, `src/app.js` | candidates and sequences, canvas rendering of rows and the sheet, the page |
| `build.py` | inlines everything into `dist/index.html` (about 1.3 MB) |
| `test/` | Node harnesses: inference vs PyTorch, detector vs the Python detector on identical scenes, the bundle end to end |
| `publish.sh` | uploads to Blossom and publishes the kind 35129 manifest with `nak` |

Build and publish:

```
glyphbyte train --out glyphbyte/data/model-small.onnx --backdrops bench/backdrops   # or use the bundled small model
python -c "from glyphbyte.model import export_weights, SMALL; export_weights('glyphbyte/data/model-small.pt', 'napplet/weights.bin', SMALL)"
python napplet/build.py napplet/weights.bin napplet/weights.bin.json
BLOSSOM=https://your.blossom RELAYS="wss://relay.damus.io" NAK_KEY="--sec nsec1..." napplet/publish.sh
```

The sandbox has no downloads, so the rendered row is meant to be copied by eye or
screenshotted. The page uses the camera through a file input, which needs no permission
from the shell. If the shell ever offers the `relay` NAP, the decoded prefix can be turned
into an event lookup right there; today the page just gives you the hex.

The Python package keeps the bigger reference model and the `glyphbyte serve` web app for
anyone who wants a server anyway.

## Install

```
git clone https://embassy.local:52248/arkin0x/glyphbyte.git   # or your mirror
cd glyphbyte
pip install .            # runtime: numpy, opencv-python-headless, onnxruntime
pip install '.[train]'   # to retrain
```

Python 3.10 or newer. The bundled model is `glyphbyte/data/model.onnx`.

## Benchmark

See `BENCH.md` for the current numbers on the synthetic suite and how to reproduce
them. Real handwriting on real walls has not been measured yet: photograph some, put
the truth in a `truth.jsonl` next to the images, and `glyphbyte bench` scores it the same
way.

## License

Two licenses, by kind of thing:

- **Code** (the Python package, the JavaScript package, the napplet, the site build, tests,
  scripts): MIT, see `LICENSE-MIT`.
- **The GlyphByte specification, the glyph alphabet and its canonical shapes, the printable
  sheet, the test vectors, and all documentation and site text**: Creative Commons
  Attribution-ShareAlike 4.0 International, see `LICENSE-CC-BY-SA-4.0`. Anyone may copy,
  adapt and build on the alphabet and the spec, including commercially, as long as they credit
  GlyphByte and share adaptations under the same license.
