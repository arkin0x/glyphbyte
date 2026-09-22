"""Generate the spec's machine-readable assets from the reference implementation.

  spec/glyphs.json         canonical polygons of the 16 glyphs (unit box, y down, upright)
  spec/glyphs.svg          the glyph sheet: 16 rows x (4 rotations outline, 4 rotations filled), square/circle frames
  spec/test-vectors.json   all 256 bytes decoded, plus byte sequences with their glyph descriptions and rendered rows
  spec/vectors/row-*.png   reference renderings of the sequences
"""
import json, os, shutil, sys
import cv2, numpy as np
from glyphbyte.symbols import SYMBOLS, unpack, load_canonical
from glyphbyte.render import render_row, shapes, rot_matrix

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SPEC = os.path.join(ROOT, "spec")
SEQUENCES = ["00", "ff", "8a3a3a6609eb", "e8ed3798c6ff", "0123456789abcdef", "deadbeef"]


def svg_sheet(path, cell=64, margin=8):
    rows, cols = 16, 8
    pitch = cell + margin
    W, H = cols * pitch + margin + 120, rows * pitch + margin
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="sans-serif" font-size="12">',
           f'<rect width="{W}" height="{H}" fill="white"/>']
    sw = max(1.5, cell * 0.045)
    for s in range(16):
        y0 = margin + s * pitch
        out.append(f'<text x="{margin}" y="{y0 + cell / 2 + 4}" fill="#333">{s:x} {SYMBOLS[s]}</text>')
        for c in range(cols):
            fill, rot = divmod(c, 4)
            frame = (s + c) % 2
            cx, cy = 120 + margin + c * pitch + cell / 2, y0 + cell / 2
            if frame:
                out.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{cell / 2:.1f}" fill="none" stroke="black" stroke-width="{sw:.1f}"/>')
            else:
                out.append(f'<rect x="{cx - cell / 2:.1f}" y="{cy - cell / 2:.1f}" width="{cell}" height="{cell}" fill="none" stroke="black" stroke-width="{sw:.1f}"/>')
            size = cell * (0.56 if frame else 0.62)
            R = rot_matrix(rot * np.pi / 2)
            sh = shapes()[s]
            d = ""
            for poly in [sh["outer"]] + sh["features"]:
                pts = (poly @ R.T) * size + [cx, cy]
                d += "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in pts) + " Z "
            out.append(f'<path d="{d.strip()}" fill="{"black" if fill else "none"}" fill-rule="evenodd" stroke="black" stroke-width="{sw:.1f}" stroke-linejoin="round"/>')
    out.append("</svg>")
    open(path, "w").write("\n".join(out))


def main():
    os.makedirs(os.path.join(SPEC, "vectors"), exist_ok=True)
    json.dump(load_canonical(), open(os.path.join(SPEC, "glyphs.json"), "w"))
    svg_sheet(os.path.join(SPEC, "glyphs.svg"))
    byte_table = []
    for b in range(256):
        g = unpack(b)
        byte_table.append({"byte": b, "hex": f"{b:02x}", "symbol": g.name, "symbol_index": g.symbol, "rotation_deg": g.rotation * 90,
                           "fill": "filled" if g.fill else "outline", "frame": "circle" if g.frame else "square", "text": g.describe()})
    seqs = []
    for hx in SEQUENCES:
        data = bytes.fromhex(hx)
        row = render_row(data, cell=120)
        name = f"vectors/row-{hx}.png"
        cv2.imwrite(os.path.join(SPEC, name), row.canvas)
        seqs.append({"hex": hx, "glyphs": [unpack(b).describe() for b in data], "image": name})
    photos = []
    src = os.path.join(ROOT, "..", "photo-01-arkinox-prefix.jpg")
    if os.path.exists(src):
        shutil.copy(src, os.path.join(SPEC, "vectors", "photo-01.jpg"))
        photos.append({"image": "vectors/photo-01.jpg", "expected": "e8ed3798c6ff",
                       "note": "marker on a dot-grid notebook, 2026-09-22; the snowman's circles are nearly equal, so a reader may rank c6 and ce close"})
    json.dump({"version": "0.1", "bit_layout": "byte = symbol_index << 4 | rotation_quarter_turns_cw << 2 | fill << 1 | frame",
               "symbols": SYMBOLS, "bytes": byte_table, "sequences": seqs, "photos": photos},
              open(os.path.join(SPEC, "test-vectors.json"), "w"), indent=1)
    print("wrote spec assets:", os.listdir(SPEC))


if __name__ == "__main__":
    main()
