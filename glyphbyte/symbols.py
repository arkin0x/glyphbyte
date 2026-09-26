"""Vocabulary and bit layout (glyphbyte v2). Everything else derives from this file.

One glyph carries one byte, drawn inside a square frame:
  high nibble  which of the 16 upright icons (see icons.py)
  low nibble   corner dots: top-left 8, top-right 4, bottom-right 2, bottom-left 1
"""

from __future__ import annotations

from dataclasses import dataclass

from .icons import NAMES

FORMAT_VERSION = 2
SYMBOLS = list(NAMES)
DOT_NAMES = ["top-left", "top-right", "bottom-right", "bottom-left"]   # bit 3, 2, 1, 0

# frame kinds as the detector reports them; v2 glyphs always use a square frame
FRAME_SQUARE = 0
FRAME_CIRCLE = 1


@dataclass(frozen=True)
class Glyph:
    icon: int       # 0..15
    dots: int       # 0..15, bit 3 top-left, 2 top-right, 1 bottom-right, 0 bottom-left

    @property
    def name(self) -> str:
        return SYMBOLS[self.icon]

    @property
    def byte(self) -> int:
        return pack(self.icon, self.dots)

    def dot_corners(self) -> list[str]:
        return [DOT_NAMES[i] for i in range(4) if self.dots >> (3 - i) & 1]

    def describe(self) -> str:
        c = self.dot_corners()
        return f"{self.name}, " + ("no dots" if not c else ("dots " if len(c) > 1 else "dot ") + ", ".join(c))


def pack(icon: int, dots: int) -> int:
    if not (0 <= icon < 16 and 0 <= dots < 16):
        raise ValueError(f"out of range: icon={icon} dots={dots}")
    return icon << 4 | dots


def unpack(byte: int) -> Glyph:
    if not 0 <= byte < 256:
        raise ValueError(f"not a byte: {byte}")
    return Glyph(icon=byte >> 4, dots=byte & 15)


FORMATS = (1, 2)
DEFAULT_FORMAT = 2


def describe(byte: int, fmt: int = DEFAULT_FORMAT) -> str:
    """One line describing the drawing of `byte` in format `fmt`."""
    if fmt == 1:
        from . import v1
        return v1.unpack(byte).describe()
    return unpack(byte).describe()


def crc8(data: bytes, poly: int = 0x07, init: int = 0x00) -> int:
    """CRC-8/ATM (poly 0x07). One trailing glyph carries it when --crc is used."""
    crc = init
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = ((crc << 1) ^ poly) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc
