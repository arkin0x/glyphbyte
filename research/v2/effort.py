"""Human side of the comparison: what does it take to draw each glyph?

Counts come straight from each set's primitives. The time estimate is a model,
anchored where possible on Quick, Draw! medians computed from Google's raw
data (line 0.5 s, circle 1.4 s, triangle 1.9 s, square 2.3 s, hexagon 4.1 s,
octagon 6.0 s: seconds for a whole one-shape drawing), and on assumptions
where no data exists (a dot 0.3 s, filling a shape 3 s per cell area).
It is a ranking aid, not a measurement; a timed trial with real people is
the measurement.

Usage: python effort.py  ->  out/effort.json and a printed table
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))

from sets import SETS  # noqa: E402

T_LINE, T_CIRCLE, T_DOT, T_FILL_PER_AREA = 0.5, 1.4, 0.3, 3.0


def t_polygon(corners: int) -> float:
    """Least-squares line through Quick, Draw! triangle/square/hexagon/octagon medians."""
    return max(T_CIRCLE, 0.84 * corners - 0.7)


def sharp_corners(outline: np.ndarray, min_turn_deg: float = 50) -> tuple[int, float]:
    """Corners where the pen must stop and turn, and the total absolute turning (degrees)."""
    p = np.asarray(outline, float)
    # resample by arc length
    seg = np.linalg.norm(np.diff(np.vstack([p, p[:1]]), axis=0), axis=1)
    s = np.concatenate([[0], np.cumsum(seg)])
    n = 240
    t = np.linspace(0, s[-1], n, endpoint=False)
    q = np.stack([np.interp(t, s, np.append(p[:, 0], p[0, 0])), np.interp(t, s, np.append(p[:, 1], p[0, 1]))], 1)
    k = 6
    a = q - np.roll(q, k, 0)
    b = np.roll(q, -k, 0) - q
    ang = np.degrees(np.arctan2(a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0], (a * b).sum(1)))
    total = float(np.abs(np.degrees(np.arctan2(
        (q - np.roll(q, 1, 0))[:, 0] * (np.roll(q, -1, 0) - q)[:, 1] - (q - np.roll(q, 1, 0))[:, 1] * (np.roll(q, -1, 0) - q)[:, 0],
        ((q - np.roll(q, 1, 0)) * (np.roll(q, -1, 0) - q)).sum(1)))).sum())
    peaks = 0
    for i in range(n):
        if abs(ang[i]) >= min_turn_deg and abs(ang[i]) >= abs(ang[i - 1]) and abs(ang[i]) > abs(ang[(i + 1) % n]):
            peaks += 1
    return peaks, total


def v1_effort(byte: int, shapes) -> dict:
    sym, fill, frame = byte >> 4, (byte >> 1) & 1, byte & 1
    outline = np.asarray(shapes[sym]["outer"], float)
    corners, turning = sharp_corners(outline)
    area = abs(float(np.sum(outline[:, 0] * np.roll(outline[:, 1], -1) - np.roll(outline[:, 0], -1) * outline[:, 1])) / 2)
    ratio = 0.62 if frame == 0 else 0.56   # glyph size relative to the frame, as drawn
    fill_area = area * ratio ** 2 if fill else 0.0
    t = (t_polygon(4) if frame == 0 else T_CIRCLE) + t_polygon(corners) + fill_area * T_FILL_PER_AREA
    return {
        "marks": 2 + (1 if fill else 0),
        "sharp_corners": corners + (4 if frame == 0 else 0),
        "oblique_strokes": None,
        "fill_area": fill_area,
        "must_recall_shape": 1,
        "must_rotate_shape": 1 if (byte >> 2) & 3 else 0,
        "things_to_get_right": 4,     # which pictogram, its rotation, filled or not, which frame
        "est_seconds": t,
    }


def prim_effort(prims) -> dict:
    lines = [p for p in prims if p[0] == "line"]
    dots = [p for p in prims if p[0] == "dot"]
    rings = [p for p in prims if p[0] == "ring"]
    # radius lines on one axis through the centre become one stroke when both are present
    strokes = 0
    used = set()
    for i, a in enumerate(lines):
        if i in used:
            continue
        for j, b in enumerate(lines):
            if j <= i or j in used:
                continue
            if abs(a[1]) < 1e-6 and abs(a[2]) < 1e-6 and abs(b[1]) < 1e-6 and abs(b[2]) < 1e-6 \
                    and abs(a[3] + b[3]) < 1e-6 and abs(a[4] + b[4]) < 1e-6:
                used.add(j)
                break
        used.add(i)
        strokes += 1
    oblique = sum(1 for p in lines if abs(p[3] - p[1]) > 1e-6 and abs(p[4] - p[2]) > 1e-6)
    t = len(rings) * T_CIRCLE + strokes * T_LINE + len(dots) * T_DOT
    return {
        "marks": len(rings) + strokes + len(dots),
        "sharp_corners": 0,
        "oblique_strokes": oblique,
        "fill_area": 0.0,
        "must_recall_shape": 0,
        "must_rotate_shape": 0,
        "things_to_get_right": len(lines) + len(dots),
        "est_seconds": t,
    }


def main():
    from glyphbyte.symbols import load_canonical
    shapes = load_canonical()
    out = {}
    for name, fn in SETS.items():
        rows = [v1_effort(b, shapes) if name == "v1" else prim_effort(fn(b)) for b in range(256)]
        agg = {}
        for k in rows[0]:
            vals = [r[k] for r in rows if r[k] is not None]
            if vals:
                agg[k] = {"mean": round(float(np.mean(vals)), 3), "max": round(float(np.max(vals)), 3)}
        out[name] = agg
    json.dump(out, open(HERE / "out" / "effort.json", "w"), indent=1)
    keys = ["marks", "sharp_corners", "oblique_strokes", "fill_area", "things_to_get_right", "est_seconds"]
    print(f"{'set':7s} " + " ".join(f"{k:>22s}" for k in keys))
    for name, agg in out.items():
        cells = []
        for k in keys:
            v = agg.get(k)
            cells.append(f"{v['mean']:>10.2f} (max {v['max']:>5.2f})" if v else f"{'-':>22s}")
        print(f"{name:7s} " + " ".join(cells))
    # per-pictogram corner counts for the record
    print("v1 sharp corners per pictogram:",
          {s["name"]: sharp_corners(np.asarray(s["outer"], float))[0] for s in shapes})


if __name__ == "__main__":
    main()
