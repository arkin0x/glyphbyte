"""Candidate glyph sets for glyphbyte v2, defined as pen primitives.

Every set maps a byte (0..255) to a list of primitives in unit coordinates:
the glyph's delimiter spans [-0.5, 0.5] on both axes, y points down, "up" is -y.

Primitives
  ("ring", cx, cy, r)            a closed circle, drawn as one stroke
  ("line", x0, y0, x1, y1)       a straight stroke
  ("dot", cx, cy, r)             a small filled blob, drawn as one tap or scribble
  ("v1", byte)                   the current glyphbyte v1 cell, drawn by glyphbyte.render

The same primitives drive the renderer (with a hand-drawing model) and the
human-effort model, so both measures see exactly the same glyph.
"""

from __future__ import annotations

import math

R = 0.5  # delimiter radius in unit coordinates

# Positions used by the ring sets. Clockwise from the top, most significant bit first.
CARDINAL = [(0, -1), (1, 0), (0, 1), (-1, 0)]                     # N E S W
DIAGONAL = [(-1, -1), (1, -1), (1, 1), (-1, 1)]                   # NW NE SE SW
DIAG_UNIT = [(x / math.sqrt(2), y / math.sqrt(2)) for x, y in DIAGONAL]


def _spokes(mask4: int, dirs, inner: float = 0.0) -> list[tuple]:
    """Radius lines from the centre (or from `inner`) to the ring, one per set bit, MSB first."""
    out = []
    for i, (dx, dy) in enumerate(dirs):
        if mask4 >> (len(dirs) - 1 - i) & 1:
            out.append(("line", dx * inner * R, dy * inner * R, dx * R, dy * R))
    return out


def _dots(mask4: int, rad: float = 0.36, size: float = 0.075) -> list[tuple]:
    out = []
    for i, (dx, dy) in enumerate(DIAG_UNIT):
        if mask4 >> (3 - i) & 1:
            out.append(("dot", dx * rad * 2 * R, dy * rad * 2 * R, size))
    return out


# --------------------------------------------------------------------------------------- sets

def v1(byte: int) -> list[tuple]:
    return [("v1", byte)]


def ring(byte: int) -> list[tuple]:
    """High nibble = four spokes N E S W, low nibble = four quadrant dots NW NE SE SW."""
    return [("ring", 0, 0, R)] + _spokes(byte >> 4, CARDINAL) + _dots(byte & 15)


def star(byte: int) -> list[tuple]:
    """Lines only: eight spokes, N NE E SE S SW W NW, MSB first."""
    dirs = [(0, -1), DIAG_UNIT[1], (1, 0), DIAG_UNIT[2], (0, 1), DIAG_UNIT[3], (-1, 0), DIAG_UNIT[0]]
    return [("ring", 0, 0, R)] + _spokes(byte, dirs)


def dice(byte: int) -> list[tuple]:
    """Dots only: 0-3 dots in each quadrant (two bits per quadrant), NW NE SE SW."""
    out = [("ring", 0, 0, R)]
    for q, (dx, dy) in enumerate(DIAG_UNIT):
        n = byte >> (6 - 2 * q) & 3
        # dots on a short line across the quadrant's bisector
        cx, cy = dx * 0.62 * R, dy * 0.62 * R
        px, py = -dy, dx  # perpendicular to the bisector
        offs = {0: [], 1: [0.0], 2: [-0.11, 0.11], 3: [-0.19, 0.0, 0.19]}[n]
        for o in offs:
            out.append(("dot", cx + px * o, cy + py * o, 0.06))
    return out


def tally(byte: int) -> list[tuple]:
    """Lines only, no diagonals: in each quadrant 0-3 short strokes parallel to the
    quadrant's axis... kept for comparison with the 'more lines' suggestion."""
    out = [("ring", 0, 0, R)]
    for q, (dx, dy) in enumerate(DIAG_UNIT):
        n = byte >> (6 - 2 * q) & 3
        cx, cy = dx * 0.58 * R, dy * 0.58 * R
        offs = {0: [], 1: [0.0], 2: [-0.07, 0.07], 3: [-0.12, 0.0, 0.12]}[n]
        for o in offs:  # vertical ticks side by side
            out.append(("line", cx + o, cy - 0.11, cx + o, cy + 0.11))
    return out


def sun(value: int) -> list[tuple]:
    """12 bits: the ring set's byte in the low 8 bits, plus four short rays outside the
    ring on the diagonals (NW NE SE SW) in the high 4 bits, like a child's drawing of the sun."""
    out = ring(value & 0xFF)
    for i, (dx, dy) in enumerate(DIAG_UNIT):
        if value >> (11 - i) & 1:
            out.append(("line", dx * 1.12 * R, dy * 1.12 * R, dx * 1.5 * R, dy * 1.5 * R))
    return out


SETS = {"v1": v1, "ring": ring, "star": star, "dice": dice, "tally": tally, "sun": sun}
BITS = {name: 8 for name in SETS} | {"sun": 12}

DESCRIPTIONS = {
    "v1": "current: 16 pictograms x 4 rotations x outline/filled x square/circle frame",
    "ring": "circle + up to 4 spokes (N E S W) + up to 4 quadrant dots",
    "star": "circle + up to 8 spokes (cardinal and diagonal), lines only",
    "dice": "circle + 0-3 dots in each quadrant",
    "tally": "circle + 0-3 short upright strokes in each quadrant",
    "sun": "ring + up to 4 short rays outside the circle on the diagonals (12 bits)",
}
