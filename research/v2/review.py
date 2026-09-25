"""Build out/review.html: the v2 glyph set proposal page for review."""

from __future__ import annotations

import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))

from icons import ICONS, KEPT, NAMES  # noqa: E402
from sets import ring  # noqa: E402

DOTS = [(-1, -1), (1, -1), (1, 1), (-1, 1)]   # NW NE SE SW = 8 4 2 1
REPLACED = {
    "tree": ("tee", "a hollow T took 8 corners; a lollipop tree is a circle and one line"),
    "plus": ("u", "a hollow U took 8 corners; a plus is two straight strokes, drawable by age 4"),
    "flag": ("l", "a hollow L took 6 corners; a flag is a pole and one triangle"),
    "box": ("cloud", "four straight lines instead of a bumpy outline; kept small so it never reads as a second frame"),
    "x": ("snowman", "two straight strokes; the frame's sides tell it apart from the plus"),
    "bolt": ("bookmark", "bookmark, trapezoid and chevron read as house or triangle once rotation is gone"),
    "star": ("trapezoid", "a five-point star is one stroke that people already draw"),
    "fish": ("chevron", "a fish is unmistakable and faces sideways, unlike every other icon"),
}


def icon_svg(name, cx, cy, size, sw):
    out = []
    for st in ICONS[name]:
        if st[0] == "circle":
            out.append(f'<circle cx="{cx + st[1] * size:.2f}" cy="{cy + st[2] * size:.2f}" r="{st[3] * size:.2f}" fill="none"/>')
        else:
            pts = " ".join(f"{cx + x * size:.2f},{cy + y * size:.2f}" for x, y in st[1])
            tag = "polygon" if st[2] else "polyline"
            out.append(f'<{tag} points="{pts}" fill="none"/>')
    return "".join(out)


def cell_svg(byte, x, y, s, sw, frame=True, icon=True, dots=True):
    cx, cy = x + s / 2, y + s / 2
    parts = []
    if frame:
        parts.append(f'<rect x="{x + sw / 2:.2f}" y="{y + sw / 2:.2f}" width="{s - sw:.2f}" height="{s - sw:.2f}" fill="none"/>')
    if icon:
        parts.append(icon_svg(NAMES[byte >> 4], cx, cy, s * 0.52, sw))
    if dots:
        for i, (dx, dy) in enumerate(DOTS):
            if byte >> (3 - i) & 1:
                parts.append(f'<circle class="dot" cx="{cx + dx * s * 0.36:.2f}" cy="{cy + dy * s * 0.36:.2f}" r="{s * 0.065:.2f}"/>')
    return "".join(parts)


def svg(w, h, body, label, sw):
    return (f'<svg viewBox="0 0 {w:.0f} {h:.0f}" role="img" aria-label="{label}" '
            f'stroke="currentColor" stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round">{body}</svg>')


def row_svg(data: bytes, s=100, sw=4):
    pitch = s * 1.22
    W = 40 + pitch * len(data) + 10
    H = s + 56
    body = [cell_svg(b, 40 + i * pitch, 6, s, sw) for i, b in enumerate(data)]
    ly = s + 34
    body.append(f'<line x1="22" y1="{ly}" x2="{W - 8}" y2="{ly}"/>')
    body.append(f'<circle class="dot" cx="22" cy="{ly}" r="{s * 0.12:.1f}"/>')
    return svg(W, H, "".join(body), "a row of glyphs on an underline with a start dot", sw)


def v1_row(data: bytes, s=100, sw=4):
    """The current set, rendered from its canonical outlines."""
    import numpy as np
    from glyphbyte.render import shapes
    from glyphbyte.symbols import unpack
    pitch = s * 1.22
    W = 40 + pitch * len(data) + 10
    H = s + 56
    body = []
    for i, b in enumerate(data):
        g = unpack(b)
        x, y = 40 + i * pitch, 6
        cx, cy = x + s / 2, y + s / 2
        if g.frame == 0:
            body.append(f'<rect x="{x + sw / 2}" y="{y + sw / 2}" width="{s - sw}" height="{s - sw}" fill="none"/>')
        else:
            body.append(f'<circle cx="{cx}" cy="{cy}" r="{s / 2 - sw / 2}" fill="none"/>')
        ratio = 0.62 if g.frame == 0 else 0.56
        th = g.rotation * math.pi / 2
        R = np.array([[math.cos(th), -math.sin(th)], [math.sin(th), math.cos(th)]])
        pts = shapes()[g.symbol]["outer"] @ R.T * s * ratio + [cx, cy]
        fill = "currentColor" if g.fill else "none"
        body.append(f'<polygon points="{" ".join(f"{p[0]:.1f},{p[1]:.1f}" for p in pts)}" fill="{fill}"/>')
    ly = s + 34
    body.append(f'<line x1="22" y1="{ly}" x2="{W - 8}" y2="{ly}"/>')
    body.append(f'<circle class="dot" cx="22" cy="{ly}" r="{s * 0.12:.1f}"/>')
    return svg(W, H, "".join(body), "the current set", sw)


def ring_row(data: bytes, s=100, sw=4):
    pitch = s * 1.22
    W = 40 + pitch * len(data) + 10
    H = s + 56
    body = []
    for i, b in enumerate(data):
        cx, cy = 40 + i * pitch + s / 2, 6 + s / 2
        for p in ring(b):
            if p[0] == "ring":
                body.append(f'<circle cx="{cx}" cy="{cy}" r="{s / 2 - sw / 2}" fill="none"/>')
            elif p[0] == "line":
                body.append(f'<line x1="{cx + p[1] * s}" y1="{cy + p[2] * s}" x2="{cx + p[3] * s}" y2="{cy + p[4] * s}"/>')
            else:
                body.append(f'<circle class="dot" cx="{cx + p[1] * s}" cy="{cy + p[2] * s}" r="{p[3] * s}"/>')
    ly = s + 34
    body.append(f'<line x1="22" y1="{ly}" x2="{W - 8}" y2="{ly}"/>')
    body.append(f'<circle class="dot" cx="22" cy="{ly}" r="{s * 0.12:.1f}"/>')
    return svg(W, H, "".join(body), "the ring set", sw)


def main():
    pk = bytes.fromhex("e8ed3798c6ff")
    hexes = "".join(f'<span>{b:02x}</span>' for b in pk)

    icons = []
    for n in range(16):
        name = NAMES[n]
        tag = '<span class="tag kept">kept</span>' if name in KEPT else '<span class="tag new">new</span>'
        icons.append(f'<figure class="tile">{svg(100, 100, cell_svg(n << 4, 0, 0, 100, 3.2, dots=False), name, 3.2)}'
                     f'<figcaption><b class="hex">{n:x}</b> {name} {tag}</figcaption></figure>')
    dots = []
    for n in range(16):
        dots.append(f'<figure class="tile">{svg(100, 100, cell_svg(n, 0, 0, 100, 3.2, icon=False), f"dots {n:x}", 3.2)}'
                    f'<figcaption><b class="hex">{n:x}</b> {n:04b}</figcaption></figure>')

    chart = ['<div class="chart"><div></div>']
    chart += [f'<div class="ch">{c:x}</div>' for c in range(16)]
    for r in range(16):
        chart.append(f'<div class="ch">{r:x}</div>')
        for c in range(16):
            b = r << 4 | c
            chart.append(f'<div title="{b:02x}">{svg(100, 100, cell_svg(b, 0, 0, 100, 4), f"{b:02x}", 4)}</div>')
    chart.append("</div>")

    swaps = "".join(f'<tr><td>{old}</td><td>{new}</td><td>{why}</td></tr>' for new, (old, why) in REPLACED.items())

    html = TEMPLATE.format(
        draft_row=row_svg(pk), v1_row=v1_row(pk), ring_row=ring_row(pk), hexes=hexes,
        icons="".join(icons), dots="".join(dots), chart="".join(chart), swaps=swaps,
        example=svg(100, 100, cell_svg(0xE8, 0, 0, 100, 3.2), "byte e8", 3.2),
    )
    (HERE / "out" / "review.html").write_text(html)
    print("wrote out/review.html", len(html) // 1024, "KB")


TEMPLATE = """<title>Glyphbyte v2 Draft Set</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@500;700;800&family=IBM+Plex+Sans:wght@400;600&family=IBM+Plex+Mono:wght@400;600&display=swap">
<style>
:root {{
  --paper: #f4f5f1; --card: #ffffff; --ink: #1b1f1d; --muted: #5a635e; --rule: #d8dcd4;
  --accent: #1f5fad; --accent-soft: #e3ecf7; --good: #2f7d4f; --warn: #a86412;
  --display: "Archivo", "Helvetica Neue", Arial, sans-serif;
  --body: "IBM Plex Sans", "Segoe UI", system-ui, sans-serif;
  --mono: "IBM Plex Mono", ui-monospace, Menlo, monospace;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --paper: #121513; --card: #1a1e1b; --ink: #e6ebe6; --muted: #9aa39d; --rule: #2e3530;
    --accent: #86b4ee; --accent-soft: #1d2a3a; --good: #6fc393; --warn: #e0a55a; color-scheme: dark;
  }}
}}
:root[data-theme="dark"] {{
  --paper: #121513; --card: #1a1e1b; --ink: #e6ebe6; --muted: #9aa39d; --rule: #2e3530;
  --accent: #86b4ee; --accent-soft: #1d2a3a; --good: #6fc393; --warn: #e0a55a; color-scheme: dark;
}}
body {{ background: var(--paper); color: var(--ink); font: 16px/1.6 var(--body); }}
main {{ max-width: 1040px; margin: 0 auto; padding-inline: 20px; padding-block: 40px 80px; display: grid; gap: 56px; }}
h1, h2, h3 {{ font-family: var(--display); line-height: 1.15; text-wrap: balance; margin: 0; }}
h1 {{ font-size: clamp(2rem, 5vw, 3.2rem); font-weight: 800; letter-spacing: -0.02em; }}
h2 {{ font-size: 1.6rem; font-weight: 700; }}
h3 {{ font-size: 1.1rem; font-weight: 700; }}
p {{ margin: 0; max-width: 68ch; }}
section {{ display: grid; gap: 18px; }}
.eyebrow {{ font: 600 0.78rem/1 var(--mono); letter-spacing: 0.12em; text-transform: uppercase; color: var(--accent); }}
.lede {{ font-size: 1.15rem; color: var(--muted); }}
svg {{ display: block; width: 100%; height: auto; overflow: visible; }}
.dot {{ fill: currentColor; stroke: none; }}
.hero {{ background: var(--card); border: 1px solid var(--rule); border-radius: 10px; padding: 24px; display: grid; gap: 10px; }}
.rowwrap {{ overflow-x: auto; }}
.rowwrap svg {{ min-width: 560px; max-width: 820px; }}
.hexrow {{ display: flex; gap: 0; font: 600 1.1rem var(--mono); color: var(--muted); padding-left: 4.9%; min-width: 560px; max-width: 820px; }}
.hexrow span {{ width: 16.1%; text-align: center; }}
.grid16 {{ display: grid; grid-template-columns: repeat(8, minmax(0, 1fr)); gap: 12px; }}
@media (max-width: 700px) {{ .grid16 {{ grid-template-columns: repeat(4, minmax(0, 1fr)); }} }}
.tile {{ margin: 0; display: grid; gap: 6px; }}
.tile svg {{ color: var(--ink); }}
.tile figcaption {{ font-size: 0.85rem; color: var(--muted); display: flex; gap: 6px; align-items: baseline; flex-wrap: wrap; }}
.hex {{ font-family: var(--mono); color: var(--ink); }}
.tag {{ font: 600 0.68rem/1 var(--mono); letter-spacing: 0.06em; text-transform: uppercase; padding: 3px 5px; border-radius: 4px; }}
.tag.kept {{ background: var(--rule); color: var(--muted); }}
.tag.new {{ background: var(--accent-soft); color: var(--accent); }}
.how {{ display: grid; grid-template-columns: 140px 1fr; gap: 24px; align-items: center; }}
@media (max-width: 560px) {{ .how {{ grid-template-columns: 1fr; }} .how svg {{ max-width: 140px; }} }}
.how ol {{ margin: 0; padding-left: 1.2em; display: grid; gap: 6px; }}
.tablewrap {{ overflow-x: auto; }}
table {{ border-collapse: collapse; width: 100%; font-size: 0.95rem; }}
th, td {{ text-align: left; vertical-align: top; padding: 10px 12px; border-bottom: 1px solid var(--rule); }}
th {{ font: 600 0.78rem var(--mono); letter-spacing: 0.06em; text-transform: uppercase; color: var(--muted); }}
td.num {{ font-variant-numeric: tabular-nums; font-family: var(--mono); }}
.pick {{ background: var(--accent-soft); }}
.compare {{ display: grid; gap: 14px; }}
.compare figure {{ margin: 0; display: grid; gap: 4px; }}
.compare figcaption {{ font-size: 0.9rem; color: var(--muted); }}
.evidence {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 14px; }}
.ev {{ border-top: 3px solid var(--accent); padding-top: 10px; display: grid; gap: 6px; }}
.ev p {{ font-size: 0.95rem; }}
.ev a {{ font-size: 0.8rem; color: var(--muted); word-break: break-all; }}
.decide {{ counter-reset: d; display: grid; gap: 14px; padding: 0; margin: 0; list-style: none; }}
.decide li {{ counter-increment: d; display: grid; grid-template-columns: 2.2rem 1fr; gap: 10px; }}
.decide li::before {{ content: counter(d); font: 800 1.5rem/1 var(--display); color: var(--accent); }}
.chart {{ display: grid; grid-template-columns: 1.4rem repeat(16, minmax(0, 1fr)); gap: 3px; min-width: 720px; }}
.chart .ch {{ font: 600 0.8rem var(--mono); color: var(--muted); display: grid; place-items: center; }}
.chart svg {{ color: var(--ink); }}
.chartwrap {{ overflow-x: auto; background: var(--card); border: 1px solid var(--rule); border-radius: 10px; padding: 14px; }}
a {{ color: var(--accent); }}
.note {{ font-size: 0.9rem; color: var(--muted); }}
</style>
<main>

<header class="hero">
  <div class="eyebrow">glyphbyte v2 · draft for review · 2026-09-25</div>
  <h1>Sixteen icons, four dots, one byte</h1>
  <p class="lede">Each glyph is a square frame holding one upright icon, which gives the first hex digit, and up to four corner dots, which give the second. That is 8 bits per glyph, the same as today, with no rotations and no filled shapes. Below is your prefix <b class="hex">e8ed3798c6ff</b> written in the draft.</p>
  <div class="rowwrap">{draft_row}<div class="hexrow">{hexes}</div></div>
</header>

<section>
  <div class="eyebrow">first hex digit</div>
  <h2>The icon alphabet</h2>
  <p>Eight icons are kept from the current set (pacman renamed pie and turned to face away from the moon). Eight are new, replacing shapes that were slow to draw or that looked too much like each other once rotation is gone. Every icon is upright, has a name you can say, and takes one or two pen strokes.</p>
  <div class="grid16">{icons}</div>
</section>

<section>
  <div class="eyebrow">second hex digit</div>
  <h2>The corner dots</h2>
  <p>Read clockwise from the top-left corner: top-left is worth 8, top-right 4, bottom-right 2, bottom-left 1. Dots never touch the icon or the frame, so they stay separate blobs even in thick chalk.</p>
  <div class="grid16">{dots}</div>
</section>

<section>
  <div class="eyebrow">worked example</div>
  <h2>Writing the byte e8</h2>
  <div class="how">{example}
    <ol>
      <li>Draw the square frame.</li>
      <li>First digit <b class="hex">e</b>: draw the star, upright.</li>
      <li>Second digit <b class="hex">8</b> is binary 1000: one dot in the top-left corner.</li>
      <li>Repeat for each byte, left to right, above one underline that starts with a fat dot.</li>
    </ol>
  </div>
</section>

<section>
  <div class="eyebrow">three directions</div>
  <h2>How it compares</h2>
  <div class="compare">
    <figure><div class="rowwrap">{v1_row}</div><figcaption>A. Current set: 16 pictograms × 4 rotations × outline or filled × square or circle frame.</figcaption></figure>
    <figure><div class="rowwrap">{draft_row}</div><figcaption>B. Draft: 16 upright icons × 16 corner-dot patterns, always a square frame.</figcaption></figure>
    <figure><div class="rowwrap">{ring_row}</div><figcaption>C. Ring, inspired by the Matoran alphabet: up to four lines from the centre, plus up to four dots, inside a circle.</figcaption></figure>
  </div>
  <div class="tablewrap"><table>
    <thead><tr><th>criterion</th><th>A current</th><th class="pick">B draft</th><th>C ring</th></tr></thead>
    <tbody>
      <tr><td>bits per glyph</td><td class="num">8</td><td class="num pick">8</td><td class="num">8</td></tr>
      <tr><td>personality, memorability</td><td>high: named pictograms</td><td class="pick">high: 16 named icons, 10 of them yours</td><td>low: abstract line patterns</td></tr>
      <tr><td>drawing: sharp corners per glyph</td><td class="num">about 6.6, up to 12</td><td class="pick">4 for the frame, plus 0 to 7 in the icon (crown and star have the most)</td><td class="num">0</td></tr>
      <tr><td>drawing: hard parts</td><td>drawing a pictogram sideways or upside down, filling it in</td><td class="pick">none; dots are taps</td><td>none</td></tr>
      <tr><td>drawing time, modelled</td><td class="num">about 5.6 s</td><td class="pick">about 5.3 s with a square frame, about 4.1 s with a circle</td><td class="num">about 2.8 s</td></tr>
      <tr><td>finding "up"</td><td>underline only</td><td class="pick">every icon is upright, so each glyph shows it too</td><td>underline only</td></tr>
      <tr><td>chalk and crop fields</td><td>fills smear and blur</td><td class="pick">outlines and dots only</td><td>outlines and dots only</td></tr>
      <tr><td>reading accuracy, small test model</td><td>pen 93%, marker 96%, chalk 83%, crop 98%</td><td class="pick">not trained yet</td><td>not trained yet</td></tr>
    </tbody>
  </table></div>
  <p class="note">Drawing times come from a simple model anchored on Google's Quick, Draw! medians: line 0.5 s, circle 1.4 s, triangle 1.9 s, square 2.3 s. A dot is assumed to take 0.3 s. These rank the options; a timed trial with real people would measure them. B and C are untrained because the set should be agreed on looks first.</p>
</section>

<section>
  <div class="eyebrow">what changed and why</div>
  <h2>Six icons replaced</h2>
  <div class="tablewrap"><table>
    <thead><tr><th>old</th><th>new</th><th>reason</th></tr></thead>
    <tbody>{swaps}</tbody>
  </table></div>
</section>

<section>
  <div class="eyebrow">evidence</div>
  <h2>What the research says</h2>
  <div class="evidence">
    <div class="ev"><h3>Lines and circles come first</h3><p>Children copy a vertical line at 2, a circle at 3, a cross and a square at 4, a triangle at 5, a diamond at 6. Slanted lines are harder than level ones at every age.</p><a href="https://med.stanford.edu/content/dam/sm/pediatricsclerkship/documents/5-Developmental-Milestones-MedU.pdf">Stanford pediatrics milestones</a><a href="https://pubmed.ncbi.nlm.nih.gov/3559475/">diamond vs square, PubMed 3559475</a></div>
    <div class="ev"><h3>Rotations and mirrors confuse people</h3><p>Left-right mirrors are the most confused transform in children's letter tests, and 180° turns nearly as much. The current set spends 2 of its 8 bits on rotation.</p><a href="https://upload.wikimedia.org/wikipedia/commons/b/b3/A_developmental_study_of_the_discrimination_of_letter-like_forms.pdf">Gibson et al. 1962</a><a href="https://pubmed.ncbi.nlm.nih.gov/19770045/">Dehaene et al. 2010</a></div>
    <div class="ev"><h3>Open vs closed is easy to tell</h3><p>Even 4-year-olds tell a closed shape from one with a gap. The draft keeps closed icons (heart, star) apart from open ones (arrow, bolt).</p><a href="https://upload.wikimedia.org/wikipedia/commons/b/b3/A_developmental_study_of_the_discrimination_of_letter-like_forms.pdf">Gibson et al. 1962</a></div>
    <div class="ev"><h3>Count to four, no further</h3><p>Up to about four items are counted at a glance and almost without error; beyond that, errors climb. Four corner dots stay inside that limit.</p><a href="https://pubmed.ncbi.nlm.nih.gov/8121961/">Trick and Pylyshyn 1994</a></div>
    <div class="ev"><h3>Simple shapes, one stroke, seconds</h3><p>In Google's Quick, Draw! data, a circle is drawn in about 1.4 s and recognised 97% of the time; a star in 3.1 s at 96%; an octagon takes 6 s.</p><a href="https://github.com/googlecreativelab/quickdraw-dataset">Quick, Draw! dataset</a></div>
    <div class="ev"><h3>Matoran: circle, lines, small circles</h3><p>Every letter sits in the same outer circle and uses one to three lines and one or two small circles. Letters that differ only by where one dot sits (A, C, P, Q, U) are its weak spot.</p><a href="https://biosector01.com/wiki/Matoran_Alphabet">BIONICLE Matoran alphabet</a></div>
    <div class="ev"><h3>Markers people can draw</h3><p>d-touch and Artcodes read hand-drawn markers by counting separate blobs inside regions. They work because blobs never touch their region's edge, which is the rule the corner dots follow.</p><a href="https://eprints.whiterose.ac.uk/id/eprint/117835/7/pref548-preston.pdf">Artcodes, DIS 2017</a></div>
    <div class="ev"><h3>Chalk and fields need big, simple marks</h3><p>A QR code cut in a cornfield only scanned after the paths were re-tilled dark; circles survive camera tilt best because they stay ellipses.</p><a href="https://www.cbc.ca/news/canada/edmonton/alberta-family-celebrates-world-record-for-qr-code-1.1251202">Kraay farm QR maze</a></div>
  </div>
</section>

<section>
  <div class="eyebrow">your calls</div>
  <h2>Three decisions before training</h2>
  <ol class="decide">
    <li><p><b>Direction.</b> B keeps the character of your set and removes what made it hard to draw. C is the easiest to draw but has no personality. A stays as it is. My recommendation is B.</p></li>
    <li><p><b>The eight new icons.</b> Tree, box, plus, flag, x, bolt, star and fish are proposals. Swap any. A replacement should be upright, nameable, one or two strokes, have no dot inside, and not be a turned or mirrored copy of another icon.</p></li>
    <li><p><b>Frame.</b> A square gives the dots natural corners. A circle is quicker to draw and survives camera tilt better, but the icon would shrink to leave room for the dots. In the drawing-time model the square frame is the biggest single cost in B: 2.3 s of about 5.3 s, against 1.4 s for a circle.</p></li>
  </ol>
</section>

<section>
  <div class="eyebrow">reference</div>
  <h2>All 256 glyphs</h2>
  <p>Row is the first hex digit (icon), column the second (dots).</p>
  <div class="chartwrap">{chart}</div>
</section>

</main>
"""

if __name__ == "__main__":
    main()
