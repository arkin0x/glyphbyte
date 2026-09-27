"""Format v1 (2026-09-22), kept so v1 rows still read and can still be drawn.

One glyph is one byte:
  bits 7..4  which of 16 pictograms
  bits 3..2  rotation, quarter turns clockwise
  bit 1      fill: 0 outline, 1 filled
  bit 0      frame: 0 square, 1 circle

The pictograms are polygons in data/glyphs-v1.json (unit box, y down, rotation 0),
extracted from the hand-drawn reference sheet in assets/.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from importlib import resources

import cv2
import numpy as np

FORMAT = 1
SYMBOLS = ["house", "chevron", "bookmark", "crown", "drop", "tee", "u", "mountain",
           "arrow", "heart", "crescent", "cloud", "snowman", "l", "trapezoid", "pacman"]
FRAME_SQUARE, FRAME_CIRCLE = 0, 1


@dataclass(frozen=True)
class Glyph:
    symbol: int
    rotation: int
    fill: int
    frame: int

    @property
    def name(self) -> str:
        return SYMBOLS[self.symbol]

    @property
    def byte(self) -> int:
        return pack(self.symbol, self.rotation, self.fill, self.frame)

    def describe(self) -> str:
        return (f"{self.name} rotated {self.rotation * 90} deg, {'filled' if self.fill else 'outline'}, "
                f"{'circle' if self.frame else 'square'} frame")


def pack(symbol: int, rotation: int, fill: int, frame: int) -> int:
    if not (0 <= symbol < 16 and 0 <= rotation < 4 and fill in (0, 1) and frame in (0, 1)):
        raise ValueError(f"out of range: symbol={symbol} rotation={rotation} fill={fill} frame={frame}")
    return symbol << 4 | rotation << 2 | fill << 1 | frame


def unpack(byte: int) -> Glyph:
    if not 0 <= byte < 256:
        raise ValueError(f"not a byte: {byte}")
    return Glyph(symbol=byte >> 4, rotation=(byte >> 2) & 3, fill=(byte >> 1) & 1, frame=byte & 1)


def turned(byte: int, quarter_turns: int) -> int:
    """The byte a v1 glyph reads as when the whole row is turned clockwise by quarter turns."""
    g = unpack(byte)
    return pack(g.symbol, (g.rotation + quarter_turns) % 4, g.fill, g.frame)


_SHAPES: list[dict] | None = None


def shapes() -> list[dict]:
    global _SHAPES
    if _SHAPES is None:
        with resources.files("glyphbyte.data").joinpath("glyphs-v1.json").open() as f:
            raw = json.load(f)
        assert [s["name"] for s in raw] == SYMBOLS, "glyphs-v1.json is out of sync with SYMBOLS"
        _SHAPES = [{"name": s["name"], "outer": np.asarray(s["outer"], np.float64),
                    "features": [np.asarray(p, np.float64) for p in s["features"]]} for s in raw]
    return _SHAPES


def draw_glyph(canvas: np.ndarray, glyph: Glyph, center, size: float, thickness: float, color: int = 0,
               rng: np.random.Generator | None = None, amount: float = 0.0, paper: int = 255) -> None:
    """One pictogram (no frame); size is its bounding size in pixels."""
    from .render import _px, draw_path, perturb, rot_matrix
    rng = rng or np.random.default_rng(0)
    s = shapes()[glyph.symbol]
    R = rot_matrix(glyph.rotation * math.pi / 2)
    outer_px = _px(perturb(s["outer"], rng, amount) @ R.T, center, size)
    feats_px = [_px(perturb(f, rng, amount) @ R.T, center, size) for f in s["features"]]
    if glyph.fill:
        cv2.fillPoly(canvas, [np.round(outer_px).astype(np.int32)], color, cv2.LINE_AA)
        for f in feats_px:
            cv2.fillPoly(canvas, [np.round(f).astype(np.int32)], paper, cv2.LINE_AA)
            draw_path(canvas, f, thickness, color, rng, amount)
        if amount > 0:   # a hand fill leaves a little paper showing through
            mask = np.zeros(canvas.shape[:2], np.uint8)
            cv2.fillPoly(mask, [np.round(outer_px).astype(np.int32)], 1)
            streaks = np.zeros_like(canvas)
            ang = rng.uniform(0, math.pi)
            d = np.array([math.cos(ang), math.sin(ang)])
            for _ in range(int(rng.integers(0, 10) * amount)):
                off = rng.uniform(-0.5, 0.5, size=2) * size + np.asarray(center)
                cv2.line(streaks, tuple(np.round(off - d * size).astype(int)), tuple(np.round(off + d * size).astype(int)),
                         255, 1, cv2.LINE_AA)
            lift = streaks.astype(np.float32) * (mask > 0) * rng.uniform(0.3, 0.7)
            canvas[:] = np.clip(canvas.astype(np.float32) + lift, 0, 255).astype(np.uint8)
        draw_path(canvas, outer_px, thickness, color, rng, amount)
    else:
        draw_path(canvas, outer_px, thickness, color, rng, amount)
        for f in feats_px:
            draw_path(canvas, f, thickness, color, rng, amount)


def draw_cell(canvas: np.ndarray, byte: int, center, frame_size: float, thickness: float, color: int = 0,
              rng: np.random.Generator | None = None, amount: float = 0.0, paper: int = 255) -> None:
    from .render import draw_frame
    rng = rng or np.random.default_rng(0)
    g = unpack(byte)
    ratio = (0.62 if g.frame == FRAME_SQUARE else 0.56) * (1 + rng.normal(0, 0.06 * amount))
    c = np.asarray(center, dtype=np.float64) + rng.normal(0, 0.02 * frame_size * amount, size=2)
    draw_frame(canvas, g.frame, center, frame_size, thickness, color, rng, amount)
    draw_glyph(canvas, g, c, frame_size * ratio, thickness, color, rng, amount, paper)
