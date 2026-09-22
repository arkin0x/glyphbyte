# Benchmark

Numbers are on synthetic scenes only. No real handwriting has been measured yet.

## Reproduce

```
glyphbyte backdrops --out bench/backdrops --n 48          # public-domain photos from picsum.photos
glyphbyte synth --out bench/synth/v1 --n 200 --backdrops bench/backdrops --seed 1
glyphbyte bench bench/synth/v1 --out bench/out/v1.json
```

`synth` draws 2 to 8 random bytes per scene in a hand-drawn style of random severity,
on a photo or a procedural surface (paper, wood, tiles, concrete, lined paper, dark
board with light ink), sometimes on a paper patch, under random perspective (up to
0.2), any camera roll, lighting gradients, shadows, blur, motion blur, noise and JPEG.
The whole row is always inside the picture.

## Results, 2026-09-22 (corrected canonical shapes)

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
