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

## Results

(filled in below by the current model)
