# Benchmark

Numbers are on synthetic scenes only. No real v2 handwriting has been measured yet.

## Reproduce (format v2)

```
glyphbyte backdrops --out bench/backdrops --n 48          # public-domain photos from picsum.photos
glyphbyte synth --out bench/synth/v2-ink --n 200 --backdrops bench/backdrops --seed 1 --media ink
glyphbyte synth --out bench/synth/v2 --n 200 --backdrops bench/backdrops --seed 1
glyphbyte bench bench/synth/v2-ink --out bench/out/v2-ink.json
glyphbyte bench bench/synth/v2 --out bench/out/v2.json
glyphbyte synth --out bench/synth/v1 --n 200 --backdrops bench/backdrops --seed 1 --format 1 --media ink
glyphbyte bench bench/synth/v1 --out bench/out/v1.json            # format 1 scenes (the numbers below used the suite v0.1 generated, same seed)
```

`synth` draws 2 to 8 random bytes per scene in a hand-drawn style of random severity,
on a photo or a procedural surface (paper, wood, tiles, concrete, lined paper, dark
board with light ink), sometimes on a paper patch, under random perspective (up to
0.2), any camera roll, lighting gradients, shadows, blur, motion blur, noise and JPEG.
The whole row is always inside the picture. `--media ink` is pen or marker only, like the
v1 suite; the default mixes in chalk on pavement (15%) and paths flattened into a crop
field seen from the air (15%).

## Results, 2026-09-26 (format v2)

Models: `glyphbyte/data/model.onnx` (big, channels 32-64-128-192) and `model-small.onnx`
(the browser's, 16-32-64-96), each trained 12 epochs x 40,000 synthetic patches.

### Pen and marker, `bench/synth/v2-ink` (200 scenes)

| metric | big (Python) | small (browser) |
|---|---|---|
| whole row exact (top-1) | 0.630 | 0.620 |
| truth among candidate readings | 0.650 | 0.640 |
| frames found | 0.885 | 0.894 |
| byte accuracy, where the frame count matched | 0.950 | 0.937 |
| icon right | 0.968 | 0.956 |
| dots right | 0.953 | 0.939 |

### With chalk and crop fields, `bench/synth/v2` (200 scenes)

| metric | big (Python) | small (browser) |
|---|---|---|
| whole row exact (top-1) | 0.425 | 0.385 |
| truth among candidate readings | 0.460 | 0.445 |
| frames found | 0.834 | 0.852 |
| byte accuracy, where the frame count matched | 0.882 | 0.857 |
| icon right | 0.935 | 0.922 |
| dots right | 0.889 | 0.868 |

### Reading either format (the default: `--format auto`)

The reader tries both formats on every photo. Same suites, big models; the v1 suite is the one
drawn in format 1 (`bench/synth/v1`, `--truth-format 1`).

| suite | format read right | whole row exact | truth among candidates | reading only the right format |
|---|---|---|---|---|
| format 1, `bench/synth/v1` | 0.920 | 0.560 | 0.580 | 0.555 (the v1 reader, 2026-09-25) |
| format 2, pen and marker | 0.965 | 0.630 | 0.650 | 0.630 |
| format 2, with chalk and crop | 0.965 | 0.420 | 0.450 | 0.425 |

Rows sent to the wrong format are rows that do not read correctly in the right one either, so
reading both formats costs format 2 nothing measurable, and format 1 rows read slightly better
than with the v1 reader (the grain pass and the handedness rule help them too).

### Compared with v1 (big model; v1 on its own pen-and-marker suite)

| metric | v1 (2026-09-25, after the start-dot fix) | v2 |
|---|---|---|
| whole row exact | 0.555 | 0.630 |
| frames found | 0.866 | 0.885 |
| byte accuracy, aligned | 0.943 | 0.950 |

What moved the numbers, in order:

- The glyphs vote on which way is up. In v2 scenes the underline's side was wrong in 9 of 96
  rows (a ruled line or a paper edge taken for the underline); v1 had the same 9 in 100 and no
  way to recover. With the vote, whole rows went from 0.570 to 0.630 for the big model.
- A second binarization of the blurred picture rejoins grainy strokes: frames found on the
  mixed suite went from 0.811 to 0.868 in its first test.
- Chalk and crop fields remain the weak cases at the scene level (light ink on a dark surface:
  see the buckets in the JSON reports). The first v2 small model read crop-field patches at
  0.985 and chalk at 0.88 on their own; finding the frames is what fails.

The JavaScript reader matches the Python reader: on 40 exported scenes both return 20
rows exactly, and its network matches PyTorch within 1.3e-3 in probability.

## v1 results (the first alphabet, kept for reference)

### Results, 2026-09-22 (corrected canonical shapes)

Suite `bench/synth/v1`: 200 scenes, 996 symbols, seed 1, regenerated after the canonical crown,
house, chevron and bookmark were fixed (the first extraction had flood-filled the gaps of the
symbols touching the sheet's top edge, which turned crown and house into squares). "Whole
sequence exact" means every symbol of the row read right, in order, as the top-1 answer.
"Aligned" metrics count only rows where the number of detected frames matched.

### Python, big reference model (`glyphbyte/data/model.onnx`, channels 32-64-128-192, 98.6% on held-out patches)

| metric | value |
|---|---|
| scenes | 200 |
| symbols | 996 |
| whole sequence exact (top-1) | 0.535 |

| truth among candidate sequences | 0.555 |
| frames found | 0.862 |
| symbol byte accuracy (aligned) | 0.922 |
| symbol bits | 0.946 |
| rotation bits | 0.945 |
| fill bits | 0.975 |
| frame bits | 0.969 |
| ms / image | 302 |

| bucket | exact |
|---|---|
| dark_ink | 0.561 |
| hand<0.5 | 0.649 |
| hand>=0.5 | 0.463 |
| light_ink | 0.417 |
| persp<0.1 | 0.536 |
| persp>=0.1 | 0.533 |

### Python, small napplet model (`glyphbyte/data/model-small.onnx`, channels 16-32-64-96, 97.6% on held-out patches)

| metric | value |
|---|---|
| scenes | 200 |
| symbols | 996 |
| whole sequence exact (top-1) | 0.525 |

### Napplet (JavaScript port, small model, 40 held-out scenes from the same generator)

| metric | value |
|---|---|
| frame count right | 25 / 40 |
| whole sequence exact (top-1) | 17 / 40 |
| symbol bits (matched cells) | 0.917 |
| rotation bits | 0.821 |
| fill bits | 0.972 |
| frame bits | 1.000 |
| whole byte | 0.772 |
| seconds / photo (Node, module JIT, 4000x1638 photo capped at 1280) | about 3 |

### First real photo

arkinox drew the first six bytes of his pubkey, `e8ed3798c6ff`, with a marker in a dot-grid
notebook (`projects/glyphbyte/photo-01-arkinox-prefix.jpg`). After the fixes that photo forced
(see the git log of 2026-09-22): the napplet reads it exactly, top-1; the Python pipeline reads
five of six top-1 and has the truth among its four candidate sequences. The one soft symbol is
the snowman, drawn as two blobs of nearly equal size, which the network cannot tell from an
upside-down pac-man; a clearly smaller top circle fixes that at the pen.

## Reading the numbers

- Per symbol the classifier is not the problem: 98.6% (big) and 97.6% (small) on held-out
  patches, 94 to 95% on symbol and rotation bits in whole photos.
- Whole-sequence accuracy is bounded by detection completeness: with 86% of frames found, a
  five-symbol row is complete only about half the time. Missing frames, not misread ones, are
  the main loss, and a missing symbol cannot be forked.
- Heavy hand-style roughly halves the exact rate compared to neat drawing; perspective barely
  matters; light ink on dark surfaces works as well as dark ink.
- Synthetic numbers are a floor, not a promise. One real photo has already found four bugs the
  suite never exercised. More real photos are the next measurement that matters.
