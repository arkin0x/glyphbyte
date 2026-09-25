# glyphbyte

One drawn glyph is one byte. The specification with test vectors is in [`spec/GLYPHBYTE.md`](spec/GLYPHBYTE.md). (Developed under the working name *symple* on 2026-09-22.)

Hand-drawn glyphs to bytes, offline. Draw a row of **glyphbyte** glyphs on a wall, a
notebook, a sidewalk or a field, photograph it, and `glyphbyte decode` returns the
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

## The code: one glyph, one byte (format v2)

Each glyph is a square frame with an upright **icon** in the middle and up to four
**corner dots**. The icon is the first hex digit; the dots are the second, reading
clockwise from the top-left corner: 8, 4, 2, 1.

| hex | icon | hex | icon |
|---|---|---|---|
| 0 | house | 8 | pie |
| 1 | heart | 9 | tree |
| 2 | drop | a | plus |
| 3 | moon | b | flag |
| 4 | crown | c | x |
| 5 | arrow | d | bolt |
| 6 | box | e | star |
| 7 | triangle | f | fish |

So `e8` is a star with one dot in the top-left corner, and `ff` is a fish with all four
dots. 16 icons x 16 dot patterns = 256: every byte has exactly one drawing and every
drawing is one byte. `glyphbyte sheet` renders all 256 for printing; the shapes are in
`glyphbyte/icons.py`.

v2 (2026-09-25) replaced the first alphabet of 16 pictograms x 4 rotations x outline or
filled x square or circle frame. Rotations, fills and a second frame shape were the parts
people found hard to draw; the reasoning and the evidence are in the spec and in
`research/v2/`.

## How to write a row

1. Draw a square frame for each byte, left to right, roughly the same size, with a gap
   of about a third of a frame between frames.
2. Draw the icon upright in the middle, about half the frame wide, touching nothing.
3. Add the corner dots. A dot must touch neither the frame nor the icon.
4. Underline the whole row with one stroke, and put a **fat dot at the start** of the
   underline, about a quarter of a frame across. The line tells the reader which way is
   up, the dot tells it where to start.

`glyphbyte encode e8ed3798c6ff --out row.png` renders a row to copy from, and
`--hand 0.7` shows what a sloppy one still looks like.

## Uncertainty is forked, not hidden

When a glyph could be one of two things, the decoder keeps both. The result carries
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
| frames | interiors of ink squares that hold ink; frames with a pen gap are recovered from their convex hull; a stroke-width check by ray marching rejects paper regions and thick texture; confidently round rings score lower |
| the row | the set of frames sharing a line and a smooth size trend with the highest total quality, so tiles and windows in the backdrop lose |
| baseline and start | parallel offsets scored by ink coverage in the gaps between frames; each candidate line is refined and tested for a fat end; a line with a dot beats a lined-paper line |
| rectify | homography from the frame's four corners, rotated so the baseline is horizontal |
| classify | a 4-block CNN (about 0.9M parameters) on 64x64 contrast-normalized patches, two heads: the icon (16 classes plus not-a-glyph) and the four corner dots (one yes/no each); polarity-invariant; ONNX on CPU |
| decode | joint probability over the 256 bytes per cell (icon times each dot), then a beam over cells |

The classifier is trained only on synthetic data rendered from the icon strokes:
wobble, stroke breathing, pen gaps, dots drawn as blobs, scribbles or tiny rings,
perspective, lighting, shadows, blur, noise, JPEG, on photographs and procedural
surfaces, in three media: pen or marker, chalk on pavement, and paths flattened into a
crop field. See `glyphbyte train`.

## Commands

| command | does |
|---|---|
| `glyphbyte decode IMG... [-v] [--json] [--debug out.png]` | read a photo; `--json` gives candidates and warnings; `--debug` writes the detection overlay |
| `glyphbyte encode HEX --out row.png [--hand 0.7]` | render bytes as a row |
| `glyphbyte sheet --out sheet.png` | the reference sheet, all 256 glyphs |
| `glyphbyte synth --out DIR --n 200 --backdrops DIR` | generate photo-like test scenes with ground truth |
| `glyphbyte bench DIR` | decode a synth directory and report accuracy |
| `glyphbyte backdrops --out bench/backdrops` | fetch public-domain photos from picsum.photos for synth |
| `glyphbyte train --backdrops DIR` | retrain the classifier (needs the `train` extra: torch) |

## On device: the napplet

Scanning should cost nothing per photo, so the recognizer also exists as a **napplet**
([NIP-5D](https://github.com/nostr-protocol/nips/pull/2303)): one self-contained
`index.html` that a Nostr shell loads in a sandboxed iframe. No server, no network, no
external scripts: the detector, the network weights and the icon shapes are all inline,
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

Everything in this repository, the code, the specification, the glyph alphabet and its canonical
shapes, the sheet, the test vectors and the documentation, is licensed under the Creative Commons
Attribution-ShareAlike 4.0 International License. See `LICENSE` and
https://creativecommons.org/licenses/by-sa/4.0/. Copy it, adapt it, ship it, commercially or not,
as long as you credit GlyphByte and share adaptations under the same license.
