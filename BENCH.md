# Benchmark

Numbers are on synthetic scenes only. No real handwriting has been measured yet.

## Reproduce

```
symple backdrops --out bench/backdrops --n 48          # public-domain photos from picsum.photos
symple synth --out bench/synth/v1 --n 200 --backdrops bench/backdrops --seed 1
symple bench bench/synth/v1 --out bench/out/v1.json
```

`synth` draws 2 to 8 random bytes per scene in a hand-drawn style of random severity,
on a photo or a procedural surface (paper, wood, tiles, concrete, lined paper, dark
board with light ink), sometimes on a paper patch, under random perspective (up to
0.2), any camera roll, lighting gradients, shadows, blur, motion blur, noise and JPEG.
The whole row is always inside the picture.

## Results, 2026-09-22

Suite : 200 scenes, 996 symbols, seed 1. "Whole sequence exact" means every
symbol of the row read right, in order, as the top-1 answer. "Aligned" metrics count only rows
where the number of detected frames matched, so the reading could be compared symbol by symbol.

### Python, big reference model (, channels 32-64-128-192)

| metric | value |
|---|---|
| scenes | 200 |
| symbols | 996 |
| whole sequence exact (top-1) | 0.515 |
| truth among candidate sequences | 0.540 |
| frames found | 0.874 |
| symbol byte accuracy (aligned) | 0.873 |
| symbol bits | 0.912 |
| rotation bits | 0.902 |
| fill bits | 0.959 |
| frame bits | 0.938 |
| ms / image | 245 |
| bucket | exact |
|---|---|
| dark_ink | 0.518 |
| hand<0.5 | 0.662 |
| hand>=0.5 | 0.423 |
| light_ink | 0.500 |
| persp<0.1 | 0.491 |
| persp>=0.1 | 0.544 |
| truth | read as | count |
|---|---|---|
| house | crown | 3 |
| u | trapezoid | 2 |
| drop | u | 2 |
| crown | crescent | 2 |
| pacman | crescent | 1 |
| pacman | arrow | 1 |
| pacman | drop | 1 |
| pacman | house | 1 |

### Python, small napplet model (, channels 16-32-64-96)

| metric | value |
|---|---|
| scenes | 200 |
| symbols | 996 |
| whole sequence exact (top-1) | 0.485 |
| truth among candidate sequences | 0.510 |
| frames found | 0.876 |
| symbol byte accuracy (aligned) | 0.859 |
| symbol bits | 0.900 |
| rotation bits | 0.897 |
| fill bits | 0.952 |
| frame bits | 0.938 |
| ms / image | 223 |


### Napplet (JavaScript port, 40 held-out scenes from the same generator)

| metric | value |
|---|---|
| frame count right | 25 / 40 |
| whole sequence exact (top-1) | 17 / 40 |
| symbol bits (matched cells) | 0.878 |
| rotation bits | 0.818 |
| fill bits | 0.980 |
| frame bits | 0.986 |
| whole byte | 0.757 |
| ms / scene (Node, sandboxed VM) | ~7500; about 550 in a module, a phone should land between |

## Reading the numbers

- Per symbol, the classifier is not the problem: 98% on held-out patches for the big model,
  95.5% for the small one. The bits that go wrong in whole photos are the symbol and the
  rotation, and those go wrong when the frame's rectification or the row's orientation is off.
- Whole-sequence accuracy is bounded by detection completeness: 87% of frames found means a
  five-symbol row is complete only about half the time. Missing frames, not misread ones, are
  the main loss. Forked candidates then rarely help, because a missing symbol cannot be forked.
- Heavy hand-style (hand >= 0.5) halves the exact rate compared to neat drawing. Perspective
  barely matters. Light ink on dark surfaces works as well as dark ink.
- The most confused pairs are house/crown, u/trapezoid, drop/u and crown/crescent. House and
  crown on the reference sheet are both nearly squares (a shallow roof, tiny points); a steeper
  roof and taller points when drawing would help, or slightly more distinct canonical shapes.
- Nothing here is real handwriting on real walls. That measurement is the next step and the
  one that matters.
