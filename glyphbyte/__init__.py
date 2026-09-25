"""glyphbyte: hand-drawn glyphs to bytes (format v2).

One glyph carries one byte, drawn inside a square frame:
  high nibble  which of 16 upright icons
  low nibble   corner dots: top-left 8, top-right 4, bottom-right 2, bottom-left 1
"""

from .symbols import FORMAT_VERSION, SYMBOLS, Glyph, pack, unpack, crc8

__all__ = ["FORMAT_VERSION", "SYMBOLS", "Glyph", "pack", "unpack", "crc8", "__version__"]
__version__ = "0.2.0"
