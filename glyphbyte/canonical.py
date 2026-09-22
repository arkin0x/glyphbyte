"""Extract the 16 canonical shapes from the hand-drawn reference sheet.

The sheet is a 4x4 grid of outline symbols. For each cell we take the ink,
fill its holes to get the silhouette, shrink the silhouette by half the
stroke width to approximate the drawn centerline, and keep any secondary
hole (an inner closed stroke, like ring_dot's small circle) as a "feature"
loop. Output goes to glyphbyte/data/canonical.json in a unit box.
"""

from __future__ import annotations

import json
import os
import sys

import cv2
import numpy as np

from .symbols import RETIRED, SYMBOLS

GRID = 4
RESAMPLE = 160


def resample_closed(points: np.ndarray, n: int) -> np.ndarray:
    """Evenly resample a closed polygon by arc length."""
    pts = np.asarray(points, dtype=np.float64)
    pts = np.vstack([pts, pts[:1]])
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    total = cum[-1]
    if total <= 0:
        return pts[:-1]
    targets = np.linspace(0, total, n, endpoint=False)
    out = np.empty((n, 2))
    for i, t in enumerate(targets):
        k = np.searchsorted(cum, t, side="right") - 1
        k = min(max(k, 0), len(seg) - 1)
        a = (t - cum[k]) / seg[k] if seg[k] > 0 else 0.0
        out[i] = pts[k] * (1 - a) + pts[k + 1] * a
    return out


def largest_external_contour(mask: np.ndarray) -> np.ndarray:
    cnts, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not cnts:
        raise RuntimeError("no contour")
    return max(cnts, key=cv2.contourArea).reshape(-1, 2)


def fill_holes(mask: np.ndarray) -> np.ndarray:
    """Ink plus everything it encloses. The mask is padded with background first, so a
    symbol touching the image edge (the crown's points on the sheet) does not get the gaps
    between its features counted as enclosed."""
    padded = np.pad(mask.astype(np.uint8), 1)
    h, w = padded.shape
    ff = np.zeros((h + 2, w + 2), np.uint8)
    flooded = (~padded.astype(bool)).astype(np.uint8)
    cv2.floodFill(flooded, ff, (0, 0), 2)
    outside = flooded == 2
    return (~outside).astype(np.uint8)[1:-1, 1:-1]


def _normalize(pts: np.ndarray) -> np.ndarray:
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    c = (lo + hi) / 2
    return (pts - c) / max(hi - lo)


def parametric(name: str) -> dict:
    """Replacement symbols that are not on the sheet, authored as polygons in the
    same unit box, y down, sheet orientation."""
    if name == "arrow":
        pts = [(0, -0.5), (0.5, -0.05), (0.18, -0.05), (0.18, 0.5), (-0.18, 0.5), (-0.18, -0.05), (-0.5, -0.05)]
    elif name == "l":
        pts = [(-0.42, -0.5), (-0.06, -0.5), (-0.06, 0.14), (0.42, 0.14), (0.42, 0.5), (-0.42, 0.5)]
    elif name == "trapezoid":
        pts = [(-0.27, -0.5), (0.27, -0.5), (0.5, 0.5), (-0.5, 0.5)]
    elif name == "pacman":
        a = np.radians(np.linspace(-50, 230, 120))
        pts = [(0.0, 0.0)] + list(zip(0.5 * np.cos(a), 0.5 * np.sin(a)))
    else:
        raise KeyError(name)
    outer = _normalize(resample_closed(np.array(pts, dtype=np.float64), RESAMPLE))
    return {"name": name, "outer": outer.round(5).tolist(), "features": []}


def extract(sheet_path: str, out_path: str, debug_path: str | None = None) -> list[dict]:
    img = cv2.imread(sheet_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise FileNotFoundError(sheet_path)
    img = cv2.GaussianBlur(img, (3, 3), 0)
    ink = (img < 128).astype(np.uint8)
    H, W = ink.shape
    ch, cw = H / GRID, W / GRID

    # cut by the grid: neighbouring symbols touch on the sheet, so global connected
    # components merge across cells. inside a cell, a 1px erosion breaks any bridge to a
    # neighbour's sliver and the largest component is the symbol.
    cells: dict[int, np.ndarray] = {}
    k3 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    for idx in range(GRID * GRID):
        r, c = divmod(idx, GRID)
        y0, y1 = int(round(r * ch)), int(round((r + 1) * ch))
        x0, x1 = int(round(c * cw)), int(round((c + 1) * cw))
        window = np.zeros_like(ink)
        window[y0:y1, x0:x1] = ink[y0:y1, x0:x1]
        eroded = cv2.erode(window, k3)
        n, labels, stats, _ = cv2.connectedComponentsWithStats(eroded, connectivity=8)
        if n < 2:
            raise RuntimeError(f"cell {idx}: no ink")
        biggest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        core = (labels == biggest).astype(np.uint8)
        cells[idx] = cv2.dilate(core, k3) & window

    shapes = []
    debug = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR) if debug_path else None
    for idx in range(GRID * GRID):
        m = cells[idx]
        # stroke width from the distance transform: max distance inside ink ~ half width
        dist = cv2.distanceTransform(m, cv2.DIST_L2, 5)
        half_w = float(np.percentile(dist[m > 0], 90))
        sil = fill_holes(m)
        k = max(1, int(round(half_w)))
        K = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * k + 1, 2 * k + 1))
        # the drawn centerline sits half a stroke inside the silhouette. erosion alone eats
        # convex points (a crown's spikes, a roof's apex), dilation of the interior alone fills
        # concave notches; their union keeps both to within k pixels.
        interior = (sil & (1 - m)).astype(np.uint8)
        centerline = cv2.erode(sil, K) | cv2.dilate(interior, K)
        outer = largest_external_contour(centerline)

        # holes of the ink component; the largest is the interior, the rest are inner strokes
        cnts, hier = cv2.findContours(m, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
        holes = []
        if hier is not None:
            for c, h in zip(cnts, hier[0]):
                if h[3] != -1 and cv2.contourArea(c) > 4 * half_w * half_w:
                    holes.append(c.reshape(-1, 2))
        holes.sort(key=lambda c: -cv2.contourArea(c.reshape(-1, 1, 2)))
        features = []
        for hole in holes[1:]:
            hm = np.zeros_like(m)
            cv2.fillPoly(hm, [hole.reshape(-1, 1, 2)], 1)
            hm = cv2.dilate(hm, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * k + 1, 2 * k + 1)))
            features.append(largest_external_contour(hm))

        # normalize into a unit box centered at the bbox center of the silhouette
        x, y, w, h = cv2.boundingRect(centerline)
        cx, cy = x + w / 2.0, y + h / 2.0
        s = 1.0 / max(w, h)

        def norm(c):
            return ((resample_closed(c, RESAMPLE) - [cx, cy]) * s).round(5).tolist()

        shapes.append({"name": SYMBOLS[idx], "outer": norm(outer), "features": [norm(f) for f in features]})  # renamed below if retired
        if debug is not None:
            cv2.polylines(debug, [outer.reshape(-1, 1, 2).astype(np.int32)], True, (0, 0, 255), 1)
            for f in features:
                cv2.polylines(debug, [f.reshape(-1, 1, 2).astype(np.int32)], True, (255, 0, 0), 1)

    retired = []
    for idx, old_name in RETIRED.items():
        retired.append({**shapes[idx], "name": old_name})
        shapes[idx] = parametric(SYMBOLS[idx])
    with open(out_path, "w") as f:
        json.dump(shapes, f)
    with open(os.path.join(os.path.dirname(out_path), "retired.json"), "w") as f:
        json.dump(retired, f)
    if debug is not None:
        cv2.imwrite(debug_path, debug)
    return shapes


if __name__ == "__main__":
    extract(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
    print("wrote", sys.argv[2])
