"""A decoder for the ring set with no learning at all: sample ink along each spoke and
in each quadrant of the rectified patch. If this reads the set well, the set's
features are plainly separable, and a trained model only has to add robustness.

Usage: python rules.py  ->  per-medium accuracy on the same test photos as evaluate.py
"""

from __future__ import annotations

import json
import math
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from evaluate import MARGIN, P, make_data  # noqa: E402
from draw import MEDIA  # noqa: E402

C = P / 2
RAD = P * (0.5 - MARGIN)   # ring radius in patch pixels


def ink_mask(p: np.ndarray) -> np.ndarray:
    # normalize_patch maps paper near 127 and ink toward 0
    return p < 95


def spoke_score(ink, ang):
    hits, n = 0, 0
    for r in np.linspace(0.3, 0.78, 12):
        best = False
        for w in np.linspace(-0.09, 0.09, 5):   # tolerate a spoke that misses the centre a little
            a = ang + w / r
            x, y = C + math.cos(a) * r * RAD, C + math.sin(a) * r * RAD
            xi, yi = int(round(x)), int(round(y))
            if 0 <= xi < P and 0 <= yi < P and ink[yi, xi]:
                best = True
                break
        hits += best
        n += 1
    return hits / n


def dot_score(ink, ang):
    tot, cnt = 0, 0
    for r in np.linspace(0.2, 0.72, 10):
        for da in np.linspace(-0.45, 0.45, 9):
            a = ang + da
            xi, yi = int(round(C + math.cos(a) * r * RAD)), int(round(C + math.sin(a) * r * RAD))
            if 0 <= xi < P and 0 <= yi < P:
                tot += ink[yi, xi]
                cnt += 1
    return tot / max(1, cnt)


def dot_bits(ink) -> int:
    """Dots are ink blobs separate from the ring-and-spokes skeleton (its largest component)."""
    import cv2
    n, lab, stats, cents = cv2.connectedComponentsWithStats(ink.astype(np.uint8), connectivity=8)
    if n <= 1:
        return 0
    big = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    v = 0
    for k in range(1, n):
        if k == big:
            continue
        area = stats[k, cv2.CC_STAT_AREA]
        dx, dy = cents[k][0] - C, cents[k][1] - C
        r = math.hypot(dx, dy) / RAD
        if area < 0.004 * P * P or not (0.12 < r < 0.85):
            continue
        q = {(-1, -1): 0, (1, -1): 1, (1, 1): 2, (-1, 1): 3}[(1 if dx > 0 else -1, 1 if dy > 0 else -1)]
        v |= 1 << (3 - q)
    return v


def decode(p: np.ndarray) -> int:
    ink = ink_mask(p)
    return spoke_bits(ink) | dot_bits(ink)


def spoke_bits(ink) -> int:
    v = 0
    for i, ang in enumerate([-math.pi / 2, 0, math.pi / 2, math.pi]):          # N E S W
        if spoke_score(ink, ang) >= 0.6:
            v |= 1 << (7 - i)
    return v


def main():
    res = {}
    with Pool(8) as pool:
        for m in MEDIA:
            X, y = make_data("ring", 2048, seed=5 + MEDIA.index(m), media=m, pool=pool)
            pred = np.array([decode(x) for x in X])
            acc = float((pred == y).mean())
            bits = float(np.mean([bin(int(a ^ b)).count("1") for a, b in zip(pred, y)]))
            res[m] = {"acc": round(acc, 4), "bits_wrong_per_glyph": round(bits, 4)}
            print(f"{m:7s} rules acc {acc:.3f} bit errors/glyph {bits:.3f}", flush=True)
    json.dump(res, open(HERE / "out" / "rules.json", "w"), indent=1)


if __name__ == "__main__":
    main()
