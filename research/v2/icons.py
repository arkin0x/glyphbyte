"""Draft icon alphabet for glyphbyte v2: 16 upright, nameable icons, each one to three
pen strokes built from lines, arcs and circles, no fills and no dots (dots are
reserved for the second hex digit). Coordinates: unit box [-0.5, 0.5], y down.

Each icon is a list of strokes; a stroke is ("poly", points, closed) or
("circle", cx, cy, r).
"""

from __future__ import annotations

import math

import numpy as np


def arc(cx, cy, r, a0, a1, n=24):
    t = np.radians(np.linspace(a0, a1, n))
    return [(cx + r * math.cos(a), cy + r * math.sin(a)) for a in t]


def _heart():
    t = np.linspace(0, 2 * math.pi, 80)
    x = 16 * np.sin(t) ** 3
    y = -(13 * np.cos(t) - 5 * np.cos(2 * t) - 2 * np.cos(3 * t) - np.cos(4 * t))
    return [("poly", list(zip(x / 36, y / 36 + 0.03)), True)]


def _drop():
    pts = [(0, -0.46)] + arc(0, 0.14, 0.27, -30, 210) + [(0, -0.46)]
    return [("poly", pts, False)]


def _moon():
    outer = arc(0, 0, 0.42, 60, 300)
    inner = arc(0.2, 0, 0.34, 238, 122, 24)
    return [("poly", outer + inner, True)]


def _cloud():
    """three bumps over a flat base, one stroke"""
    pts = [(-0.44, 0.2)] + arc(-0.26, 0.04, 0.18, 150, 270) + arc(0.0, -0.06, 0.24, 200, 340) \
        + arc(0.26, 0.04, 0.18, 270, 390) + [(0.44, 0.2)]
    return [("poly", pts, True)]


def _star():
    pts = []
    for k in range(5):
        a = math.radians(-90 + k * 144)
        pts.append((0.46 * math.cos(a), 0.46 * math.sin(a) + 0.04))
    return [("poly", pts, True)]


def _pie():
    """a pie missing one slice; the gap faces left, away from the moon's opening"""
    return [("poly", [(0, 0)] + arc(0, 0, 0.42, 215, 505), True)]


def _spiral():
    """one and a half turns, open, one stroke"""
    t = np.linspace(0, 3 * math.pi, 90)
    r = 0.06 + 0.36 * t / t[-1]
    return [("poly", list(zip(r * np.cos(t), r * np.sin(t))), False)]


def _umbrella():
    dome = arc(0, 0.02, 0.44, 180, 360)
    return [("poly", dome, True), ("poly", [(0, 0.02), (0, 0.36)] + arc(-0.08, 0.36, 0.08, 0, 180, 10), False)]


def _fish():
    """lens body plus a triangle tail, one stroke"""
    x = np.linspace(-0.22, 0.44, 30)
    h = 0.24 * np.sqrt(np.clip(1 - ((x - 0.11) / 0.33) ** 2, 0, 1))
    top = list(zip(x, -h))
    bottom = list(zip(x[::-1], h[::-1]))
    return [("poly", top + bottom + [(-0.46, 0.2), (-0.46, -0.2), (-0.22, 0.0)], False)]


def _wave():
    x = np.linspace(-0.45, 0.45, 60)
    return [("poly", list(zip(x, 0.16 * np.sin(x * 2 * math.pi / 0.6))), False)]


ICONS = {
    "house":    [("poly", [(-0.34, 0.42), (-0.34, -0.05), (0, -0.42), (0.34, -0.05), (0.34, 0.42)], True)],
    "heart":    _heart(),
    "drop":     _drop(),
    "moon":     _moon(),
    "crown":    [("poly", [(-0.4, 0.3), (-0.4, -0.3), (-0.2, 0.0), (0, -0.36), (0.2, 0.0), (0.4, -0.3), (0.4, 0.3)], True)],
    "arrow":    [("poly", [(0, 0.45), (0, -0.42)], False), ("poly", [(-0.3, -0.12), (0, -0.44), (0.3, -0.12)], False)],
    "box":      [("poly", [(-0.3, -0.3), (0.3, -0.3), (0.3, 0.3), (-0.3, 0.3)], True)],
    "triangle": [("poly", [(-0.45, 0.36), (0, -0.4), (0.45, 0.36)], True)],
    "pie":      _pie(),
    "tree":     [("circle", 0, -0.14, 0.28), ("poly", [(0, 0.14), (0, 0.46)], False)],
    "plus":     [("poly", [(0, -0.42), (0, 0.42)], False), ("poly", [(-0.42, 0), (0.42, 0)], False)],
    "flag":     [("poly", [(-0.3, 0.46), (-0.3, -0.44)], False), ("poly", [(-0.3, -0.44), (0.36, -0.24), (-0.3, -0.04)], False)],
    "x":        [("poly", [(-0.32, -0.32), (0.32, 0.32)], False), ("poly", [(0.32, -0.32), (-0.32, 0.32)], False)],
    "bolt":     [("poly", [(0.12, -0.46), (-0.2, 0.04), (0.16, 0.0), (-0.12, 0.46)], False)],
    "star":     _star(),
    "fish":     _fish(),
}
NAMES = list(ICONS)
KEPT = {"house", "heart", "drop", "moon", "crown", "arrow", "triangle", "pie"}

# candidates to replace the wave, not in the alphabet yet
CANDIDATES = {"spiral": _spiral(), "plus": [("poly", [(0, -0.4), (0, 0.4)], False), ("poly", [(-0.4, 0), (0.4, 0)], False)], "umbrella": _umbrella()}
