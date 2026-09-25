#!/usr/bin/env python
"""Assemble site/dist for glyphbyte.dev from the repository's own files.

usage, from the repository root with the project venv:

    python site/build.py            # rebuild site/dist from scratch, then check every internal link
    python site/build.py --check    # only run the link check on the existing site/dist

What goes where:

    napplet/dist/index.html      -> dist/app/index.html          the reader, byte for byte (built first if missing)
    spec/GLYPHBYTE.md            -> dist/spec/index.html         rendered with the `markdown` package
    spec/{test-vectors,glyphs}.json, spec/glyphs.svg, spec/vectors/*  -> dist/spec/...
    spec/glyphs.svg              -> dist/sheet.svg
    spec/vectors/row-<hex>.png   -> dist/img/                    the reference row on the landing page
    spec/glyphs.json (house)     -> dist/favicon.svg
    site/src/*                   -> dist/index.html, dist/404.html, dist/.htaccess

dist/ is deleted and rebuilt on every run so nothing stale is ever uploaded.
"""
import html
import json
import os
import re
import shutil
import subprocess
import sys
from html.parser import HTMLParser

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC, DIST = os.path.join(HERE, "src"), os.path.join(HERE, "dist")
NAPPLET, SPEC = os.path.join(ROOT, "napplet"), os.path.join(ROOT, "spec")
ROW_HEX = "e8ed3798c6ff"   # the reference row shown on the landing page
SITE_DESCRIPTION = ("GlyphByte: a hand-drawable alphabet where one glyph is one byte. Draw a nostr event id or "
                    "pubkey prefix with any pen; a phone reads it back on the device and a relay resolves it.")


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    os.chmod(path, 0o644)


def copy(src, dst):
    """copyfile, not copy2: the source mode is not carried over (a 0600 source would be unreadable on a web server)."""
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copyfile(src, dst)
    os.chmod(dst, 0o644)


def page(fragment, title, description, main_class, **fields):
    """Fill site/src/<fragment> into site/src/shell.html with the shared CSS inlined."""
    main = read(os.path.join(SRC, fragment))
    for key, value in fields.items():
        main = main.replace("{{" + key + "}}", value)
    doc = read(os.path.join(SRC, "shell.html"))
    for key, value in {"TITLE": title, "DESCRIPTION": description, "CLASS": main_class,
                       "CSS": read(os.path.join(SRC, "style.css")).strip(), "MAIN": main.strip()}.items():
        doc = doc.replace("{{" + key + "}}", value)
    left = re.findall(r"{{[A-Z_]+}}", doc)
    if left:
        raise SystemExit(f"{fragment}: unfilled placeholders {left}")
    return doc


def render_spec():
    try:
        import markdown
    except ImportError:
        raise SystemExit("the `markdown` package is missing: uv pip install --python <venv>/bin/python markdown")
    body = markdown.markdown(read(os.path.join(SPEC, "GLYPHBYTE.md")), extensions=["tables", "fenced_code", "toc", "sane_lists"])
    # tables get a scrolling container so a wide table never scrolls the whole page on a phone
    return body.replace("<table>", '<div class="table-wrap"><table>').replace("</table>", "</table></div>")


def image_size(path):
    import cv2
    h, w = cv2.imread(path, cv2.IMREAD_UNCHANGED).shape[:2]
    return w, h


def resize_photo(src, dst, max_side=1200, quality=85):
    import cv2
    im = cv2.imread(src)   # applies the EXIF orientation, as browsers do, so the copy needs no EXIF
    h, w = im.shape[:2]
    s = min(1.0, max_side / max(h, w))
    if s < 1.0:
        im = cv2.resize(im, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    cv2.imwrite(dst, im, [cv2.IMWRITE_JPEG_QUALITY, quality])
    os.chmod(dst, 0o644)
    return im.shape[1], im.shape[0]


def favicon_svg():
    """Byte 0x0f, the house with all four corner dots, from the spec's own strokes."""
    g = json.load(open(os.path.join(SPEC, "glyphs.json")))
    house = next(i for i in g["icons"] if i["name"] == "house")
    k = 52 * g["icon_scale"]
    paths = "".join(f'<polyline points="{" ".join(f"{32 + x * k:.1f},{32 + y * k:.1f}" for x, y in st["points"] + (st["points"][:1] if st["closed"] else []))}" '
                    'fill="none" stroke="#151515" stroke-width="4" stroke-linejoin="round"/>' for st in house["strokes"])
    dots = "".join(f'<circle cx="{32 + dx * g["dot_offset"] * 52:.1f}" cy="{32 + dy * g["dot_offset"] * 52:.1f}" r="{g["dot_radius"] * 52 * 1.2:.1f}" fill="#151515"/>'
                   for dx, dy in ((-1, -1), (1, -1), (1, 1), (-1, 1)))
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="12" fill="#f6f4ee"/>'
            '<rect x="6" y="6" width="52" height="52" fill="none" stroke="#151515" stroke-width="4"/>' + paths + dots + '</svg>\n')


def build():
    app = os.path.join(NAPPLET, "dist", "index.html")
    if not os.path.exists(app):
        print("napplet/dist/index.html is missing: building the napplet first")
        subprocess.run([sys.executable, "build.py", "weights.bin", "weights.bin.json"], cwd=NAPPLET, check=True)
    if os.path.isdir(DIST):
        shutil.rmtree(DIST)

    copy(app, os.path.join(DIST, "app", "index.html"))
    for name in ("test-vectors.json", "glyphs.json", "glyphs.svg"):
        copy(os.path.join(SPEC, name), os.path.join(DIST, "spec", name))
    vectors = sorted(os.listdir(os.path.join(SPEC, "vectors")))
    for name in vectors:
        copy(os.path.join(SPEC, "vectors", name), os.path.join(DIST, "spec", "vectors", name))
    copy(os.path.join(SPEC, "glyphs.svg"), os.path.join(DIST, "sheet.svg"))

    row_src = os.path.join(SPEC, "vectors", f"row-{ROW_HEX}.png")
    copy(row_src, os.path.join(DIST, "img", f"row-{ROW_HEX}.png"))
    row_w, row_h = image_size(row_src)

    tv = json.load(open(os.path.join(SPEC, "test-vectors.json")))
    seq = next(s for s in tv["sequences"] if s["hex"] == ROW_HEX)
    row_glyphs = "".join(f"<li><code>{ROW_HEX[2 * i:2 * i + 2]}</code> {html.escape(g)}</li>" for i, g in enumerate(seq["glyphs"]))

    write(os.path.join(DIST, "index.html"), page(
        "landing.html", "glyphbyte", SITE_DESCRIPTION, "landing",
        ROW_HEX=ROW_HEX, ROW_W=str(row_w), ROW_H=str(row_h), ROW_GLYPHS=row_glyphs))
    write(os.path.join(DIST, "404.html"), page(
        "404.html", "not found · glyphbyte", "This page does not exist.", "notfound"))
    vector_links = ", ".join(f'<a href="/spec/vectors/{html.escape(n)}">{html.escape(n)}</a>' for n in vectors)
    write(os.path.join(DIST, "spec", "index.html"), page(
        "spec.html", "GlyphByte specification", "The GlyphByte specification: the byte layout, the alphabet, "
        "how to draw a glyph and a row, how readers work, and how the bytes resolve on nostr.", "spec",
        SPEC_HTML=render_spec(), VECTOR_LINKS=vector_links))
    write(os.path.join(DIST, "favicon.svg"), favicon_svg())
    copy(os.path.join(SRC, "htaccess"), os.path.join(DIST, ".htaccess"))

    total = sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(DIST) for f in fs)
    print(f"built {DIST}: {total / 1e6:.2f} MB")


class Refs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.refs = []

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key in ("href", "src") and value:
                self.refs.append(value)


def check(dist=DIST):
    """Every href and src in every HTML page under dist must point at a file in dist (or be external)."""
    checked, broken = 0, []
    for dirpath, _, files in os.walk(dist):
        for name in files:
            if not name.endswith(".html"):
                continue
            path = os.path.join(dirpath, name)
            parser = Refs()
            parser.feed(read(path))
            for ref in parser.refs:
                if re.match(r"^[a-z][a-z0-9+.-]*:", ref, re.I) or ref.startswith(("#", "//")):
                    continue
                target = ref.split("#")[0].split("?")[0]
                if not target:
                    continue
                fs = os.path.join(dist, target.lstrip("/")) if target.startswith("/") else os.path.join(dirpath, target)
                fs = os.path.normpath(fs)
                if os.path.isdir(fs):
                    fs = os.path.join(fs, "index.html")
                checked += 1
                if not os.path.isfile(fs):
                    broken.append((os.path.relpath(path, dist), ref))
    for page_name, ref in broken:
        print(f"BROKEN  {page_name}: {ref}")
    print(f"link check: {checked} internal references, {len(broken)} broken")
    return not broken


if __name__ == "__main__":
    if "--check" not in sys.argv[1:]:
        build()
    sys.exit(0 if check() else 1)
