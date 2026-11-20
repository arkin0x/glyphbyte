#!/usr/bin/env python
"""Assemble site/dist for glyphbyte.dev from the repository's own files.

usage, from the repository root with the project venv:

    python site/build.py            # rebuild site/dist from scratch, then check every internal link
    python site/build.py --check    # only run the link check on the existing site/dist

What goes where:

    napplet/dist/index.html      -> dist/app/index.html          the reader, byte for byte (built first if missing)
    spec/GLYPHBYTE.md            -> dist/spec/index.html         rendered with the `markdown` package, with contents
    spec/{test-vectors,glyphs,glyphs-v1}.json, spec/glyphs{,-v1}.svg, spec/vectors/*  -> dist/spec/...
    spec/glyphs.svg              -> dist/sheet.svg
    spec/glyphs.json             -> inlined into the pages (window.GLYPHS) for the drawn and 3D glyphs; the favicon
    site/src/site.js             -> inlined: the glyph renderer and the landing page's interactive parts
    site/src/vendor/crystals.js  -> dist/vendor/crystals.js      the 3D crystals with three.js, prebuilt by
                                                                 `npm run build` in site/three (committed)
    site/src/fonts/*             -> dist/fonts/
    site/src/*.html, style.css   -> dist/index.html, dist/404.html, dist/.htaccess

Templates take {{NAME}} placeholders and {{icon:name}} for an inline icon from site/src/icons.json (Lucide, ISC).
dist/ is deleted and rebuilt on every run so nothing stale is ever uploaded. Needs only the `markdown` package.
"""
import hashlib
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
SITE_ORIGIN = "https://www.glyphbyte.dev"   # the served origin: Vercel redirects the bare domain here
SITE_DESCRIPTION = ("Like QR codes you can memorize and draw: any page, file or link on the internet can be found with "
                    "about six hand-drawn glyphs, and any phone camera brings it back.")


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


ICONS = None


def icons(text):
    """{{icon:name}} -> an inline Lucide SVG that takes the text colour."""
    global ICONS
    if ICONS is None:
        ICONS = json.load(open(os.path.join(SRC, "icons.json")))

    def one(m):
        if m.group(1) not in ICONS:
            raise SystemExit(f"unknown icon {m.group(1)}: add it to site/src/icons.json")
        return f'<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">{ICONS[m.group(1)]}</svg>'
    return re.sub(r"{{icon:([a-z0-9-]+)}}", one, text)


def glyphs():
    g = json.load(open(os.path.join(SPEC, "glyphs.json")))
    return {k: g[k] for k in ("icon_scale", "dot_offset", "dot_radius", "icons")}


def mark_svg(size=None, page=False, square=False, favicon=False):
    """The glyphbyte mark: byte 0x0f, the house with all four corner dots, in a frame of split light.
    favicon: the logo as it is in the top bar (no tile, cropped close), with strokes a little heavier for
    16 px, and a house that turns light on a dark tab bar."""
    g = glyphs()
    house = next(i for i in g["icons"] if i["name"] == "house")
    k = 40 * g["icon_scale"]
    pts = lambda st: " ".join(f"{32 + x * k:.1f},{32 + y * k:.1f}" for x, y in st["points"] + (st["points"][:1] if st["closed"] else []))
    ink = "#0d0f1c" if (page or favicon) else "currentColor"
    sw = 4.6 if favicon else 3.6
    roof = "".join(f'<polyline class="ink" points="{pts(st)}" fill="none" stroke="{ink}" stroke-width="{sw}" stroke-linejoin="round" stroke-linecap="round"/>' for st in house["strokes"])
    dots = "".join(f'<circle cx="{32 + dx * g["dot_offset"] * 40:.1f}" cy="{32 + dy * g["dot_offset"] * 40:.1f}" r="{g["dot_radius"] * 40 * (1.25 if favicon else 1.1):.1f}" fill="url(#gbp)"/>'
                   for dx, dy in ((-1, -1), (1, -1), (1, 1), (-1, 1)))
    bg = ('<rect width="64" height="64" fill="#f5f6fb"/>' if square else '<rect width="64" height="64" rx="16" fill="#f5f6fb"/>') if page and not favicon else ""
    dark = '<style>@media (prefers-color-scheme: dark) { .ink { stroke:#eef0ff } }</style>' if favicon else ""
    dim = f' width="{size}" height="{size}"' if size else ""
    # on the page the mark is cropped close, so it reads big; an app icon (square) keeps a margin for the OS mask
    box = "6 6 52 52" if square else "8.5 8.5 47 47" if favicon else "0 0 64 64" if page else "9 9 46 46"
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{box}"{dim} aria-hidden="true"><defs><linearGradient id="gbp" x1="0" y1="0" x2="1" y2="1">'
            '<stop offset="0" stop-color="#3fc6ff"/><stop offset=".35" stop-color="#6d7bff"/><stop offset=".65" stop-color="#b76bff"/><stop offset="1" stop-color="#ff6fae"/></linearGradient></defs>'
            f'{dark}{bg}<rect x="12" y="12" width="40" height="40" rx="3" fill="none" stroke="url(#gbp)" stroke-width="{sw}"/>{roof}{dots}</svg>')


def inline_module(path):
    """An ES module's text as a classic script: its exports become page globals."""
    src = read(path)
    src = re.sub(r"^export (async function|function|const|let|class) ", r"\1 ", src, flags=re.M)
    if re.search(r"^\s*(import|export)\b", src, re.M):
        raise SystemExit(f"{path}: has imports or exports this inliner does not handle")
    return src


def scripts(crystals=False):
    out = [f"<script>window.GLYPHS = {json.dumps(glyphs(), separators=(',', ':'))};</script>",
           f"<script>\n{read(os.path.join(SRC, 'site.js'))}\n</script>"]
    if crystals:
        out.append('<script type="module" src="/vendor/crystals.js"></script>')
    return "\n".join(out)


def page(fragment, title, description, body_class, crystals=False, nav_spec=False, path="/", **fields):
    """Fill site/src/<fragment> into site/src/shell.html with the shared CSS and scripts inlined."""
    main = read(os.path.join(SRC, fragment))
    for key, value in fields.items():
        main = main.replace("{{" + key + "}}", value)
    doc = read(os.path.join(SRC, "shell.html"))
    for key, value in {"TITLE": title, "DESCRIPTION": description, "CLASS": body_class, "CSS": read(os.path.join(SRC, "style.css")).strip(),
                       "BRAND": mark_svg(), "URL": SITE_ORIGIN + path, "ORIGIN": SITE_ORIGIN, "NAV_SPEC": ' aria-current="page"' if nav_spec else "", "SCRIPTS": scripts(crystals), "MAIN": main.strip()}.items():
        doc = doc.replace("{{" + key + "}}", value)
    doc = icons(doc)
    left = re.findall(r"{{[A-Za-z_:-]+}}", doc)
    if left:
        raise SystemExit(f"{fragment}: unfilled placeholders {left}")
    return doc


def render_spec():
    try:
        import markdown
    except ImportError:
        raise SystemExit("the `markdown` package is missing: uv pip install --python <venv>/bin/python markdown")
    md = markdown.Markdown(extensions=["tables", "fenced_code", "toc", "sane_lists"])
    body = md.convert(read(os.path.join(SPEC, "GLYPHBYTE.md")))
    # tables get a scrolling container so a wide table never scrolls the whole page on a phone
    body = body.replace("<table>", '<div class="table-wrap"><table>').replace("</table>", "</table></div>")
    # contents: the sections under the title
    tokens = md.toc_tokens
    sections = tokens[0]["children"] if len(tokens) == 1 and tokens[0]["level"] == 1 else tokens
    toc = "<ul>" + "".join(f'<li><a href="#{t["id"]}">{t["name"]}</a></li>' for t in sections) + "</ul>"
    return body, toc


def build():
    app = os.path.join(NAPPLET, "dist", "index.html")
    if not os.path.exists(app):
        print("napplet/dist/index.html is missing: building the napplet first")
        subprocess.run([sys.executable, "build.py", "weights.bin", "weights.bin.json"], cwd=NAPPLET, check=True)
    if os.path.isdir(DIST):
        shutil.rmtree(DIST)

    copy(app, os.path.join(DIST, "app", "index.html"))
    for name in ("test-vectors.json", "glyphs.json", "glyphs.svg", "glyphs-v1.json", "glyphs-v1.svg"):
        copy(os.path.join(SPEC, name), os.path.join(DIST, "spec", name))
    vectors = sorted(os.listdir(os.path.join(SPEC, "vectors")))
    for name in vectors:
        copy(os.path.join(SPEC, "vectors", name), os.path.join(DIST, "spec", "vectors", name))
    copy(os.path.join(SPEC, "glyphs.svg"), os.path.join(DIST, "sheet.svg"))
    for name in sorted(os.listdir(os.path.join(SRC, "fonts"))):
        copy(os.path.join(SRC, "fonts", name), os.path.join(DIST, "fonts", name))
    copy(os.path.join(SRC, "vendor", "crystals.js"), os.path.join(DIST, "vendor", "crystals.js"))

    write(os.path.join(DIST, "index.html"), page(
        "landing.html", "GlyphByte: anything online in six glyphs", SITE_DESCRIPTION, "landing", crystals=True))
    write(os.path.join(DIST, "404.html"), page(
        "404.html", "Not found · GlyphByte", "This page does not exist.", "notfound", path="/404.html"))
    vector_links = ", ".join(f'<a href="/spec/vectors/{html.escape(n)}">{html.escape(n)}</a>' for n in vectors)
    spec_html, spec_toc = render_spec()
    write(os.path.join(DIST, "spec", "index.html"), page(
        "spec.html", "GlyphByte specification", "The GlyphByte specification: the byte layout, the alphabet, "
        "how to draw a glyph and a row, how readers work, and how a row is looked up.", "spec", nav_spec=True, path="/spec/",
        SPEC_HTML=spec_html, SPEC_TOC=spec_toc, VECTOR_LINKS=vector_links))
    write(os.path.join(DIST, "favicon.svg"), mark_svg(favicon=True) + "\n")
    # social images and app icons: rendered by site/og/render.mjs into site/src/og/ (committed)
    og_dir = os.path.join(SRC, "og")
    for name in sorted(os.listdir(og_dir)) if os.path.isdir(og_dir) else []:
        copy(os.path.join(og_dir, name), os.path.join(DIST, name))
    write(os.path.join(DIST, "site.webmanifest"), json.dumps({
        "name": "GlyphByte", "short_name": "GlyphByte", "description": SITE_DESCRIPTION, "start_url": "/app/", "scope": "/",
        "display": "standalone", "background_color": "#f5f6fb", "theme_color": "#f5f6fb",
        "icons": [{"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"}, {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"},
                  {"src": "/favicon.svg", "sizes": "any", "type": "image/svg+xml"}]}, indent=1) + "\n")
    # the page the banner is rendered from, and the square icon the app icons are rendered from
    card = read(os.path.join(HERE, "og", "card.html"))
    for key, value in {"CSS": read(os.path.join(SRC, "style.css")).strip(), "BRAND": mark_svg(),
                       "GLYPHS": json.dumps(glyphs(), separators=(",", ":"))}.items():
        card = card.replace("{{" + key + "}}", value)
    write(os.path.join(DIST, "og-card", "index.html"), card)
    write(os.path.join(DIST, "og-card", "icon.svg"), mark_svg(page=True, square=True) + "\n")
    copy(os.path.join(SRC, "htaccess"), os.path.join(DIST, ".htaccess"))

    fingerprint(DIST)
    total = sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(DIST) for f in fs)
    print(f"built {DIST}: {total / 1e6:.2f} MB")


def fingerprint(dist=DIST):
    """Cache busting: every link from a page to an image, SVG, JSON or script file gets ?v=<hash of its
    content>. Those files can be cached, and some keep their name across versions (the sheet, the 3D
    bundle), so a changed file must come with a changed link. The pages themselves are revalidated on
    every visit, so a new link reaches everyone at once."""
    cache = {}

    def stamp(m):
        attr, url = m.group(1), m.group(2)
        fs = os.path.join(dist, url.lstrip("/"))
        if not os.path.isfile(fs):
            return m.group(0)
        if fs not in cache:
            with open(fs, "rb") as f:
                cache[fs] = hashlib.sha256(f.read()).hexdigest()[:10]
        return f'{attr}="{url}?v={cache[fs]}"'

    for dirpath, _, files in os.walk(dist):
        for name in files:
            if name.endswith(".html") and not dirpath.endswith(os.sep + "app"):
                path = os.path.join(dirpath, name)
                write(path, re.sub(r'(src|href)="(/[^"?#]+\.(?:png|jpg|svg|json|js))"', stamp, read(path)))


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
