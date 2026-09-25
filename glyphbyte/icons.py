"""The 16 v2 icons as pen strokes. This file is the single source of every icon's shape.

Coordinates are a unit box centred on the origin, x right, y down; the icon is drawn
upright at about half the frame's side. Every stroke is a polyline, open or closed
(circles are polylines too), so drawing, rendering in JavaScript and the SVG sheets
all consume the same data.
"""

from __future__ import annotations

import math

import numpy as np


def _arc(cx, cy, r, a0, a1, n=24):
    t = np.radians(np.linspace(a0, a1, n))
    return [(cx + r * math.cos(a), cy + r * math.sin(a)) for a in t]


def _circle(cx, cy, r, n=40):
    return _arc(cx, cy, r, 0, 360 * (n - 1) / n, n)


def _heart():
    t = np.linspace(0, 2 * math.pi, 64, endpoint=False)
    x = 16 * np.sin(t) ** 3
    y = -(13 * np.cos(t) - 5 * np.cos(2 * t) - 2 * np.cos(3 * t) - np.cos(4 * t))
    return list(zip(x / 36, y / 36 + 0.02))


def _star():
    pts = []
    for k in range(5):
        a = math.radians(-90 + k * 144)
        pts.append((0.46 * math.cos(a), 0.46 * math.sin(a) + 0.04))
    return pts


def _fish():
    x = np.linspace(-0.22, 0.44, 24)
    h = 0.24 * np.sqrt(np.clip(1 - ((x - 0.11) / 0.33) ** 2, 0, 1))
    return list(zip(x, -h)) + list(zip(x[::-1], h[::-1])) + [(-0.46, 0.2), (-0.46, -0.2), (-0.22, 0.0)]


# (name, [(points, closed), ...]); the index is the first hex digit
ICONS: list[tuple[str, list[tuple[list, bool]]]] = [
    ("house",    [([(-0.34, 0.42), (-0.34, -0.05), (0, -0.42), (0.34, -0.05), (0.34, 0.42)], True)]),
    ("heart",    [(_heart(), True)]),
    ("drop",     [([(0, -0.46)] + _arc(0, 0.14, 0.27, -30, 210) + [(0, -0.46)], False)]),
    ("moon",     [(_arc(0, 0, 0.42, 60, 300) + _arc(0.2, 0, 0.34, 238, 122), True)]),
    ("crown",    [([(-0.4, 0.3), (-0.4, -0.3), (-0.2, 0.0), (0, -0.36), (0.2, 0.0), (0.4, -0.3), (0.4, 0.3)], True)]),
    ("arrow",    [([(0, 0.45), (0, -0.42)], False), ([(-0.3, -0.12), (0, -0.44), (0.3, -0.12)], False)]),
    ("box",      [([(-0.3, -0.3), (0.3, -0.3), (0.3, 0.3), (-0.3, 0.3)], True)]),
    ("triangle", [([(-0.45, 0.36), (0, -0.4), (0.45, 0.36)], True)]),
    ("pie",      [([(0, 0)] + _arc(0, 0, 0.42, 215, 505), True)]),
    ("tree",     [(_circle(0, -0.14, 0.28), True), ([(0, 0.14), (0, 0.46)], False)]),
    ("plus",     [([(0, -0.42), (0, 0.42)], False), ([(-0.42, 0), (0.42, 0)], False)]),
    ("flag",     [([(-0.3, 0.46), (-0.3, -0.44)], False), ([(-0.3, -0.44), (0.36, -0.24), (-0.3, -0.04)], False)]),
    ("x",        [([(-0.32, -0.32), (0.32, 0.32)], False), ([(0.32, -0.32), (-0.32, 0.32)], False)]),
    ("bolt",     [([(0.12, -0.46), (-0.2, 0.04), (0.16, 0.0), (-0.12, 0.46)], False)]),
    ("star",     [(_star(), True)]),
    ("fish",     [(_fish(), False)]),
]

NAMES = [n for n, _ in ICONS]
ICON_SCALE = 0.48          # icon size relative to the frame side
DOT_OFFSET = 0.32          # dot centres sit this far from the frame centre on each axis, in frame sides
DOT_RADIUS = 0.065         # dot radius in frame sides
# with these three, every dot clears both the icon and the frame by 0.115 frame sides, clean
DOT_CORNERS = [(-1, -1), (1, -1), (1, 1), (-1, 1)]   # top-left 8, top-right 4, bottom-right 2, bottom-left 1


def strokes(icon: int) -> list[tuple[np.ndarray, bool]]:
    return [(np.asarray(p, np.float64), closed) for p, closed in ICONS[icon][1]]


def as_json() -> list[dict]:
    """The icons for JavaScript and SVG: [{"name", "strokes": [{"points", "closed"}]}]."""
    return [{"name": n, "strokes": [{"points": [[round(float(x), 4), round(float(y), 4)] for x, y in p], "closed": c}
                                    for p, c in s]} for n, s in ICONS]
