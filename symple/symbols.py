"""Vocabulary and bit layout. Everything else derives from this file."""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources

# Sheet order, left to right, top to bottom. Index is the high nibble of the byte.
SYMBOLS = [
    "house",       # 0  square body, pointed roof
    "chevron",     # 1  house whose base is cut by a chevron
    "bookmark",    # 2  rectangle with a chevron cut into the bottom
    "crown",       # 3  rectangle with three points on top
    "drop",        # 4  teardrop, point up
    "tee",         # 5  block letter T
    "u",           # 6  block letter U
    "mountain",    # 7  triangle whose apex is split into two peaks
    "arrow",       # 8  chevron head on a shaft, pointing up      (replaced spade)
    "heart",       # 9  heart
    "crescent",    # 10 thick crescent lying like a bowl, horns up
    "cloud",       # 11 dome with three scallops underneath
    "snowman",     # 12 small circle merged onto a larger circle
    "l",           # 13 block letter L                            (replaced clover)
    "trapezoid",   # 14 narrow top, wide bottom                   (replaced shield)
    "pacman",      # 15 disc with a wedge bitten out of the top   (replaced ring_dot)
]

# Shapes on the 2026-09-22 sheet that were replaced because they differ from another
# symbol only by a small feature (see README). Kept in data/retired.json for reference.
RETIRED = {8: "spade", 13: "clover", 14: "shield", 15: "ring_dot"}

FRAME_SQUARE = 0
FRAME_CIRCLE = 1
FILL_OUTLINE = 0
FILL_FILLED = 1


@dataclass(frozen=True)
class Glyph:
    symbol: int     # 0..15
    rotation: int   # 0..3 quarter turns clockwise
    fill: int       # 0 outline, 1 filled
    frame: int      # 0 square, 1 circle

    @property
    def name(self) -> str:
        return SYMBOLS[self.symbol]

    @property
    def byte(self) -> int:
        return pack(self.symbol, self.rotation, self.fill, self.frame)

    def describe(self) -> str:
        return (f"{self.name} rotated {self.rotation * 90} deg, "
                f"{'filled' if self.fill else 'outline'}, "
                f"{'circle' if self.frame else 'square'} frame")


def pack(symbol: int, rotation: int, fill: int, frame: int) -> int:
    if not (0 <= symbol < 16 and 0 <= rotation < 4 and fill in (0, 1) and frame in (0, 1)):
        raise ValueError(f"out of range: symbol={symbol} rotation={rotation} fill={fill} frame={frame}")
    return (symbol << 4) | (rotation << 2) | (fill << 1) | frame


def unpack(byte: int) -> Glyph:
    if not 0 <= byte < 256:
        raise ValueError(f"not a byte: {byte}")
    return Glyph(symbol=byte >> 4, rotation=(byte >> 2) & 3, fill=(byte >> 1) & 1, frame=byte & 1)


def crc8(data: bytes, poly: int = 0x07, init: int = 0x00) -> int:
    """CRC-8/ATM (poly 0x07). One trailing symbol carries it when --crc is used."""
    crc = init
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = ((crc << 1) ^ poly) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


def load_canonical() -> list[dict]:
    """The 16 canonical shapes extracted from the reference sheet (see canonical.py).

    Each entry: {"name": str, "outer": [[x, y], ...], "features": [[[x, y], ...], ...]}
    in a unit box centered at the origin, y down, unrotated (sheet orientation).
    """
    with resources.files("symple.data").joinpath("canonical.json").open() as f:
        shapes = json.load(f)
    assert [s["name"] for s in shapes] == SYMBOLS, "canonical.json is out of sync with SYMBOLS"
    return shapes
