"""symple: hand-drawn symbols to bytes.

One symbol carries one byte:
  high nibble  which of the 16 symbols (sheet order)
  bits 3..2    rotation in quarter turns clockwise
  bit 1        fill: 0 outline, 1 filled
  bit 0        frame: 0 square, 1 circle
"""

from .symbols import SYMBOLS, Glyph, pack, unpack, crc8

__all__ = ["SYMBOLS", "Glyph", "pack", "unpack", "crc8", "__version__"]
__version__ = "0.1.0"
