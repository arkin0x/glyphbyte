"""Generate the spec's machine-readable assets from the reference implementation (format v2).

  spec/glyphs.json         the 16 icons as pen strokes (unit box, y down, upright) plus the frame geometry
  spec/glyphs.svg          all 256 glyphs: row = icon (first hex digit), column = corner dots (second)
  spec/test-vectors.json   all 256 bytes decoded, plus byte sequences with their glyph descriptions and rendered rows
  spec/vectors/row-*.png   reference renderings of the sequences
  spec/glyphs-v1.json      format 1's pictograms (copied from glyphbyte/data); spec/glyphs-v1.svg is its sheet
"""
import json
import os
import shutil

import cv2

from glyphbyte.icons import DOT_CORNERS, DOT_OFFSET, DOT_RADIUS, ICON_SCALE, as_json
from glyphbyte.render import render_row
from glyphbyte.symbols import DOT_NAMES, FORMAT_VERSION, SYMBOLS, unpack

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SPEC = os.path.join(ROOT, "spec")
SEQUENCES = ["00", "ff", "8a3a3a6609eb", "e8ed3798c6ff", "0123456789abcdef", "deadbeef"]
# real photographs of hand-drawn rows: (file in spec/vectors, format, expected hex, note)
PHOTOS: list[tuple[str, int, str, str]] = [
    ("v1-photo-01.jpg", 1, "e8ed3798c6ff",
     "format 1, marker on a dot-grid notebook, 2026-09-22; the snowman's circles are nearly equal, so readers may rank c6 below ce"),
    ("v1-photo-02.jpg", 1, "0c9e5e17",
     "format 1, marker on a dot-grid card on a dark table, 2026-09-25; the underline's run passes its start dot"),
]


def glyph_svg(b, x, y, s, sw):
    icons = as_json()
    cx, cy, size = x + s / 2, y + s / 2, s * ICON_SCALE
    out = [f'<rect x="{x + sw / 2:.1f}" y="{y + sw / 2:.1f}" width="{s - sw:.1f}" height="{s - sw:.1f}" fill="none"/>']
    for st in icons[b >> 4]["strokes"]:
        pts = " ".join(f"{cx + px * size:.1f},{cy + py * size:.1f}" for px, py in st["points"])
        out.append(f'<{"polygon" if st["closed"] else "polyline"} points="{pts}" fill="none"/>')
    for i, (dx, dy) in enumerate(DOT_CORNERS):
        if b >> (3 - i) & 1:
            out.append(f'<circle cx="{cx + dx * DOT_OFFSET * s:.1f}" cy="{cy + dy * DOT_OFFSET * s:.1f}" r="{DOT_RADIUS * s:.1f}" fill="black" stroke="none"/>')
    return "".join(out)


def svg_sheet(path, cell=56, margin=10):
    pitch = cell + margin
    left = 110
    W, H = left + 16 * pitch + margin, 30 + 16 * pitch + margin
    sw = max(1.5, cell * 0.04)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="sans-serif" font-size="13">',
           f'<rect width="{W}" height="{H}" fill="white"/>']
    for c in range(16):
        out.append(f'<text x="{left + c * pitch + cell / 2:.1f}" y="20" text-anchor="middle" fill="#333">{c:x}</text>')
    out.append(f'<g stroke="black" stroke-width="{sw:.1f}" stroke-linecap="round" stroke-linejoin="round">')
    for r in range(16):
        y = 30 + r * pitch
        out.append(f'<text x="{margin}" y="{y + cell / 2 + 4:.1f}" fill="#333" stroke="none">{r:x} {SYMBOLS[r]}</text>')
        for c in range(16):
            out.append(glyph_svg(r << 4 | c, left + c * pitch, y, cell, sw))
    out.append("</g></svg>")
    open(path, "w").write("\n".join(out))


def main():
    os.makedirs(os.path.join(SPEC, "vectors"), exist_ok=True)
    json.dump({"format": FORMAT_VERSION, "icon_scale": ICON_SCALE, "dot_offset": DOT_OFFSET, "dot_radius": DOT_RADIUS,
               "dot_corners": [{"bit": 3 - i, "value": 8 >> i, "corner": DOT_NAMES[i], "dx": dx, "dy": dy}
                               for i, (dx, dy) in enumerate(DOT_CORNERS)],
               "icons": as_json()}, open(os.path.join(SPEC, "glyphs.json"), "w"))
    svg_sheet(os.path.join(SPEC, "glyphs.svg"))
    shutil.copyfile(os.path.join(ROOT, "glyphbyte", "data", "glyphs-v1.json"), os.path.join(SPEC, "glyphs-v1.json"))
    byte_table = []
    for b in range(256):
        g = unpack(b)
        byte_table.append({"byte": b, "hex": f"{b:02x}", "icon": g.name, "icon_index": g.icon, "dots_value": g.dots,
                           "dots": g.dot_corners(), "text": g.describe()})
    seqs = []
    for hx in SEQUENCES:
        data = bytes.fromhex(hx)
        row = render_row(data, cell=120)
        name = f"vectors/row-{hx}.png"
        cv2.imwrite(os.path.join(SPEC, name), row.canvas)
        seqs.append({"hex": hx, "glyphs": [unpack(b).describe() for b in data], "image": name})
    photos = [{"image": f"vectors/{f}", "format": fm, "expected": hx, "note": note} for f, fm, hx, note in PHOTOS]
    json.dump({"format": FORMAT_VERSION,
               "bit_layout": "byte = icon_index << 4 | dots; dots: top-left 8, top-right 4, bottom-right 2, bottom-left 1",
               "symbols": SYMBOLS, "bytes": byte_table, "sequences": seqs, "photos": photos},
              open(os.path.join(SPEC, "test-vectors.json"), "w"), indent=1)
    print("wrote spec assets:", sorted(os.listdir(SPEC)))


if __name__ == "__main__":
    main()
