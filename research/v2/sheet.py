"""out/glyphbyte-v2-draft.png: a one-page reference sheet of the draft set, for sharing."""

from __future__ import annotations

import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))
from glyphbyte.icons import DOT_OFFSET, DOT_RADIUS, ICON_SCALE, NAMES, strokes  # noqa: E402

SS = 2                       # supersampling
W, H = 2400, 1790
PAPER = (246, 245, 240)
INK = (27, 31, 29)
MUTED = (104, 112, 107)
RULE = (214, 217, 209)
ACCENT = (31, 95, 173)
F = HERE / "fonts"


def font(name, size):
    return ImageFont.truetype(str(F / name), size * SS)


TITLE, H2, BODY, SMALL = font("DejaVuSans-Bold.ttf", 54), font("DejaVuSans-Bold.ttf", 30), font("DejaVuSans.ttf", 24), font("DejaVuSans.ttf", 20)
MONO, MONOB = font("DejaVuSansMono.ttf", 22), font("DejaVuSansMono-Bold.ttf", 26)
DOTS = [(-1, -1), (1, -1), (1, 1), (-1, 1)]


def P(v):
    return v * SS


def line(d, pts, w, closed=False):
    pts = [(P(x), P(y)) for x, y in pts]
    if closed:
        pts = pts + [pts[0], pts[1]]
    d.line(pts, fill=INK, width=int(P(w)), joint="curve")
    r = P(w) / 2
    for x, y in (pts[0], pts[-1]):
        d.ellipse([x - r, y - r, x + r, y + r], fill=INK)


def glyph(d, byte, x, y, s, w, icon=True, dots=True):
    """byte's glyph in a square of side s with top-left (x, y)."""
    m = w / 2
    line(d, [(x + m, y + m), (x + s - m, y + m), (x + s - m, y + s - m), (x + m, y + s - m)], w, closed=True)
    cx, cy, size = x + s / 2, y + s / 2, s * ICON_SCALE
    if icon:
        for pts, closed in strokes(byte >> 4):
            line(d, [(cx + a * size, cy + b * size) for a, b in pts], w, closed=closed)
    if dots:
        r = s * DOT_RADIUS
        for i, (dx, dy) in enumerate(DOTS):
            if byte >> (3 - i) & 1:
                px, py = cx + dx * s * DOT_OFFSET, cy + dy * s * DOT_OFFSET
                d.ellipse([P(px - r), P(py - r), P(px + r), P(py + r)], fill=INK)


def text(d, xy, s, f, fill=INK, anchor="la"):
    d.text((P(xy[0]), P(xy[1])), s, font=f, fill=fill, anchor=anchor)


def main():
    img = Image.new("RGB", (W * SS, H * SS), PAPER)
    d = ImageDraw.Draw(img)
    L = 90
    text(d, (L, 70), "glyphbyte v2", TITLE)
    tw = d.textlength("glyphbyte v2", font=TITLE) / SS
    text(d, (L + tw + 28, 84), "the glyph set", H2, MUTED)
    text(d, (L, 150), "One glyph carries one byte. The icon gives the first hex digit, the corner dots give the second.", BODY, MUTED)

    # icons
    def section(y, label):
        d.line([(P(L), P(y)), (P(W - L), P(y))], fill=RULE, width=P(2))
        text(d, (L, y + 22), label, H2)

    y0 = 220
    section(y0, "First hex digit: the icon")
    text(d, (L + 520, y0 + 28), "always upright, drawn small, one or two strokes", SMALL, MUTED)
    s = 210
    gap = (W - 2 * L - 8 * s) / 7
    for n in range(16):
        r, c = divmod(n, 8)
        x, y = L + c * (s + gap), y0 + 80 + r * (s + 90)
        glyph(d, n << 4, x, y, s, 6, dots=False)
        text(d, (x, y + s + 16), f"{n:x}", MONOB, ACCENT)
        text(d, (x + 30, y + s + 18), NAMES[n], BODY)

    y1 = y0 + 80 + 2 * (s + 90) + 20
    section(y1, "Second hex digit: the corner dots")
    text(d, (L + 600, y1 + 28), "top-left 8, top-right 4, bottom-right 2, bottom-left 1", SMALL, MUTED)
    s2 = 112
    gap2 = (W - 2 * L - 16 * s2) / 15
    for n in range(16):
        x, y = L + n * (s2 + gap2), y1 + 84
        glyph(d, n, x, y, s2, 4.5, icon=False)
        text(d, (x + s2 / 2, y + s2 + 14), f"{n:x}", MONOB, ACCENT, anchor="ma")
        text(d, (x + s2 / 2, y + s2 + 48), f"{n:04b}", MONO, MUTED, anchor="ma")

    y2 = y1 + 84 + s2 + 110
    section(y2, "Example: the hex prefix e8ed3798c6ff")
    data = bytes.fromhex("e8ed3798c6ff")
    s3, pitch = 190, 250
    x0 = L + 70
    for i, b in enumerate(data):
        glyph(d, b, x0 + i * pitch, y2 + 90, s3, 6)
        text(d, (x0 + i * pitch + s3 / 2, y2 + 90 + s3 + 76), f"{b:02x}", MONOB, ACCENT, anchor="ma")
        text(d, (x0 + i * pitch + s3 / 2, y2 + 90 + s3 + 112), f"{NAMES[b >> 4]} + {b & 15:04b}", SMALL, MUTED, anchor="ma")
    ly = y2 + 90 + s3 + 40
    line(d, [(L + 20, ly), (x0 + 5 * pitch + s3 + 30, ly)], 6)
    r = 24
    d.ellipse([P(L + 20 - r), P(ly - r), P(L + 20 + r), P(ly + r)], fill=INK)

    # rules, right of the example
    rx = x0 + 6 * pitch + 40
    text(d, (rx, y2 + 92), "How to write it", H2)
    rules = [
        "1  Draw a square frame.",
        "2  Draw the icon upright and small,",
        "    well inside the frame.",
        "3  Add corner dots that touch nothing.",
        "4  Write left to right above one",
        "    underline that starts with a fat dot.",
    ]
    for i, t in enumerate(rules):
        text(d, (rx, y2 + 150 + i * 40), t, BODY)

    text(d, (L, H - 70), "Format v2 · 2026-09-25 · glyphbyte.dev · CC BY-SA 4.0", SMALL, MUTED)
    img = img.resize((W, H), Image.LANCZOS)
    out = HERE / "out" / "glyphbyte-v2-sheet.png"
    img.save(out, optimize=True)
    print("wrote", out)


if __name__ == "__main__":
    main()
