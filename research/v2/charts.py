"""Clean SVG charts of the candidate sets, for review.

  out/ring-chart.svg    all 256 ring glyphs: row = first hex digit (lines), column = second (dots)
  out/ring-legend.svg   the two 16-entry tables a person needs to write any byte by hand
  out/prefix-*.svg      a prefix written in a set, on its underline with the start dot
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from sets import SETS  # noqa: E402

INK = "currentColor"


def glyph_svg(prims, cx, cy, size, sw):
    out = []
    for p in prims:
        if p[0] == "ring":
            out.append(f'<circle cx="{cx + p[1] * size:.1f}" cy="{cy + p[2] * size:.1f}" r="{p[3] * size:.1f}" fill="none" stroke="{INK}" stroke-width="{sw}"/>')
        elif p[0] == "line":
            out.append(f'<line x1="{cx + p[1] * size:.1f}" y1="{cy + p[2] * size:.1f}" x2="{cx + p[3] * size:.1f}" y2="{cy + p[4] * size:.1f}" stroke="{INK}" stroke-width="{sw}" stroke-linecap="round"/>')
        elif p[0] == "dot":
            out.append(f'<circle cx="{cx + p[1] * size:.1f}" cy="{cy + p[2] * size:.1f}" r="{p[3] * size:.1f}" fill="{INK}"/>')
    return "".join(out)


def svg(w, h, body, label):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" role="img" aria-label="{label}" '
            f'font-family="ui-monospace,Menlo,monospace">{body}</svg>\n')


def chart(set_name="ring", cell=56):
    fn = SETS[set_name]
    pad = 34
    W = H = pad + 16 * cell
    body = []
    for i in range(16):
        body.append(f'<text x="{pad + i * cell + cell / 2}" y="22" text-anchor="middle" font-size="15" fill="{INK}" opacity=".7">{i:x}</text>')
        body.append(f'<text x="14" y="{pad + i * cell + cell / 2 + 5}" text-anchor="middle" font-size="15" fill="{INK}" opacity=".7">{i:x}</text>')
    for b in range(256):
        r, c = b >> 4, b & 15
        body.append(glyph_svg(fn(b), pad + c * cell + cell / 2, pad + r * cell + cell / 2, cell * 0.78, 2.2))
    return svg(W, H, "".join(body), f"all 256 {set_name} glyphs")


def legend(cell=64):
    """Two rows of 16: lines for the first hex digit, dots for the second."""
    fn = SETS["ring"]
    pad = 90
    W, H = pad + 16 * cell, 2 * (cell + 34) + 10
    body = []
    for row, (title, f) in enumerate([("1st digit", lambda n: fn(n << 4)), ("2nd digit", lambda n: fn(n))]):
        y0 = row * (cell + 34)
        body.append(f'<text x="4" y="{y0 + cell / 2 + 5}" font-size="14" fill="{INK}">{title}</text>')
        for n in range(16):
            cx = pad + n * cell + cell / 2
            body.append(glyph_svg(f(n), cx, y0 + cell / 2, cell * 0.74, 2.2))
            body.append(f'<text x="{cx}" y="{y0 + cell + 20}" text-anchor="middle" font-size="15" fill="{INK}">{n:x}</text>')
    return svg(W, H, "".join(body), "hex digit to lines and dots")


def prefix(set_name, values, cell=80, wide=False):
    fn = SETS[set_name]
    pitch = cell * (1.75 if wide else 1.3)
    pad = cell * 0.7
    W = pad * 2 + pitch * len(values)
    H = cell * (2.4 if wide else 1.8)
    body = []
    cy = cell * (0.95 if wide else 0.75)
    for i, v in enumerate(values):
        body.append(glyph_svg(fn(v), pad + pitch * i + pitch / 2, cy, cell, 3))
    ly = cy + cell * (0.95 if wide else 0.72)
    body.append(f'<line x1="{pad * 0.6}" y1="{ly}" x2="{W - pad * 0.6}" y2="{ly}" stroke="{INK}" stroke-width="3" stroke-linecap="round"/>')
    body.append(f'<circle cx="{pad * 0.6}" cy="{ly}" r="{cell * 0.13}" fill="{INK}"/>')
    return svg(W, H, "".join(body), f"{set_name} row")


def main():
    out = HERE / "out"
    (out / "ring-chart.svg").write_text(chart("ring"))
    (out / "ring-legend.svg").write_text(legend())
    pk = bytes.fromhex("e8ed3798c6ff")
    (out / "prefix-ring.svg").write_text(prefix("ring", list(pk)))
    # the same 48 bits as four 12-bit sun glyphs
    v = int.from_bytes(pk, "big")
    suns = [(v >> (36 - 12 * i)) & 0xFFF for i in range(4)]
    (out / "prefix-sun.svg").write_text(prefix("sun", suns, wide=True))
    print("wrote charts;", "sun values", [f"{s:03x}" for s in suns])


if __name__ == "__main__":
    main()
