"""Hand-drawing model and media simulation for comparing glyph sets.

The hand model is deliberately harsher than a careful writer: rings are
ellipses that may not close, lines bow and miss the centre, dots vary in size
and are sometimes drawn as tiny circles, and the whole glyph shears and tilts.

Media turn the ink canvas into a photo of pen on paper, marker, chalk on
pavement, or a field seen from the air, then the camera adds perspective,
blur, noise and compression. The resolution of a glyph in the photo is drawn
from a wide range so small features (dots, short strokes) are tested at the
sizes a phone actually delivers.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from glyphbyte.render import draw_cell, perturb  # noqa: E402
from glyphbyte.synth import photometric, random_backdrop, random_homography  # noqa: E402

from sets import SETS  # noqa: E402

MEDIA = ["pen", "marker", "chalk", "crop"]
THICKNESS = {  # stroke width as a fraction of the delimiter diameter
    "pen": (0.02, 0.05),
    "marker": (0.05, 0.09),
    "chalk": (0.07, 0.13),
    "crop": (0.08, 0.15),
}


# ----------------------------------------------------------------------------- hand model

def _poly(canvas, pts, th, rng, hand, closed=False):
    """Stroke a polyline with breathing width."""
    n = len(pts)
    chunks = max(2, n // 6)
    idx = np.linspace(0, n - 1, chunks + 1).astype(int)
    for c in range(chunks):
        seg = pts[idx[c]:idx[c + 1] + 1]
        w = th * (1 + rng.normal(0, 0.15 * hand))
        cv2.polylines(canvas, [np.round(seg * 4).astype(np.int32)], False, 0, max(1, int(round(w))),
                      cv2.LINE_AA, shift=2)


def _ring(canvas, c, r, th, rng, hand):
    a0 = rng.uniform(0, 2 * math.pi)
    closure = rng.uniform(-0.05, 0.09) * hand           # < 0 leaves a gap, > 0 overlaps
    span = 2 * math.pi * (1 + closure)
    n = 120
    t = a0 + np.linspace(0, span, n)
    drift = np.linspace(0, rng.normal(0, 0.03) * hand, n)  # an overlap spirals in or out a little
    aspect = 1 + rng.normal(0, 0.06 * hand)
    tilt = rng.uniform(0, math.pi)
    pts = np.stack([np.cos(t) * (1 + drift) * aspect, np.sin(t) * (1 + drift) / aspect], 1) * 0.5
    ct, st = math.cos(tilt), math.sin(tilt)
    pts = pts @ np.array([[ct, -st], [st, ct]]).T
    pts = perturb(pts, rng, hand * 0.7) if hand > 0 else pts
    _poly(canvas, c + pts * 2 * r, th, rng, hand)


def _line(canvas, p0, p1, th, rng, hand, oblique):
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    d = p1 - p0
    L = np.linalg.norm(d) + 1e-9
    u = d / L
    ang = rng.normal(0, math.radians(5 if oblique else 3) * hand)   # the oblique effect
    ca, sa = math.cos(ang), math.sin(ang)
    u = np.array([u[0] * ca - u[1] * sa, u[0] * sa + u[1] * ca])
    L2 = L * (1 + rng.normal(0, 0.07 * hand))
    q0 = p0
    q1 = p0 + u * L2
    n = 32
    s = np.linspace(0, 1, n)[:, None]
    pts = q0 + (q1 - q0) * s
    bow = rng.normal(0, 0.035 * hand) * L                         # a slight arc
    nrm = np.array([-u[1], u[0]])
    pts += nrm * (bow * 4 * s * (1 - s))
    _poly(canvas, pts, th, rng, hand)


def _dot(canvas, c, r, th, rng, hand):
    r = r * rng.uniform(0.65, 1.45) if hand > 0 else r
    style = rng.random() if hand > 0 else 1.0   # a clean render draws a plain filled dot
    if style < 0.12:     # drawn as a tiny circle; with a thick tool it usually fills in
        cv2.circle(canvas, tuple(np.round(c * 4).astype(int)), int(round(r * 0.8 * 4)), 0,
                   max(1, int(round(max(th, r * 0.6)))), cv2.LINE_AA, shift=2)
    elif style < 0.35:   # a scribbled blob
        k = 12
        t = np.linspace(0, 2 * math.pi, k, endpoint=False)
        rr = r * (1 + rng.normal(0, 0.2, k))
        pts = np.stack([c[0] + rr * np.cos(t), c[1] + rr * np.sin(t)], 1)
        cv2.fillPoly(canvas, [np.round(pts * 4).astype(np.int32)], 0, cv2.LINE_AA, shift=2)
    else:
        cv2.circle(canvas, tuple(np.round(c * 4).astype(int)), int(round(r * 4)), 0, -1, cv2.LINE_AA, shift=2)


def render_glyph(set_name: str, byte: int, cell: float, thickness: float, hand: float,
                 rng: np.random.Generator, pad: float = 0.45):
    """Ink canvas (255 paper, 0 ink) and the delimiter's corners (tl, tr, br, bl)."""
    W = H = int(cell * (1 + 2 * pad))
    canvas = np.full((H, W), 255, np.uint8)
    C = np.array([W / 2, H / 2])
    prims = SETS[set_name](byte)
    if prims[0][0] == "v1":
        draw_cell(canvas, byte, tuple(C), cell, thickness, 0, rng, hand)
    else:
        # the writer eyeballs the centre once, and every spoke aims at that point
        centre_err = rng.normal(0, 0.035 * hand, 2)
        shear = np.eye(2) + rng.normal(0, 0.05 * hand, (2, 2))
        tilt = rng.normal(0, math.radians(4) * hand)
        ct, st = math.cos(tilt), math.sin(tilt)
        A = np.array([[ct, -st], [st, ct]]) @ shear

        def P(x, y):
            return C + (A @ np.array([x, y])) * cell

        for p in prims:
            kind = p[0]
            if kind == "ring":
                _ring(canvas, P(p[1], p[2]), p[3] * cell, thickness, rng, hand)
            elif kind == "line":
                x0, y0, x1, y1 = p[1:]
                at_centre = abs(x0) < 1e-6 and abs(y0) < 1e-6
                if at_centre:
                    over = rng.normal(0.0, 0.05 * hand)   # stop short of or overshoot the centre
                    d = np.array([x1 - x0, y1 - y0])
                    d /= np.linalg.norm(d)
                    start = np.array([centre_err[0], centre_err[1]]) - d * over
                    # draw inward from the ring, the way people draw a radius
                    end = np.array([x1, y1]) * (1 + rng.normal(0.02, 0.04 * hand))
                    oblique = abs(d[0]) > 0.2 and abs(d[1]) > 0.2
                    _line(canvas, P(*end), P(*start), thickness, rng, hand, oblique)
                else:
                    jitter = rng.normal(0, 0.02 * hand, 4)
                    _line(canvas, P(x0 + jitter[0], y0 + jitter[1]), P(x1 + jitter[2], y1 + jitter[3]),
                          thickness, rng, hand, False)
            elif kind == "dot":
                jitter = rng.normal(0, 0.035 * hand, 2)
                _dot(canvas, P(p[1] + jitter[0], p[2] + jitter[1]), p[3] * cell, thickness, rng, hand)
    h = cell / 2
    corners = np.array([[C[0] - h, C[1] - h], [C[0] + h, C[1] - h], [C[0] + h, C[1] + h], [C[0] - h, C[1] + h]])
    return canvas, corners


# ----------------------------------------------------------------------------- media

def _noise(rng, h, w, sigma):
    n = rng.normal(0, 1, (h, w)).astype(np.float32)
    return cv2.GaussianBlur(n, (0, 0), sigma) if sigma > 0 else n


def _pavement(rng, h, w):
    base = rng.uniform(40, 120)
    g = base + 18 * _noise(rng, h, w, 1.0) * 3 + 10 * _noise(rng, h, w, 6) * 6
    if rng.random() < 0.5:  # slab joints or cracks
        s = int(rng.integers(max(60, w // 3), max(61, w)))
        yy, xx = np.mgrid[0:h, 0:w]
        g[(xx % s) < 2] -= 30
    g = np.clip(g, 0, 255).astype(np.uint8)
    bgr = cv2.cvtColor(g, cv2.COLOR_GRAY2BGR).astype(np.float32) * rng.uniform(0.9, 1.1, 3)
    return np.clip(bgr, 0, 255).astype(np.uint8)


def _field(rng, h, w):
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    ang = rng.uniform(0, math.pi)
    u = xx * math.cos(ang) + yy * math.sin(ang)
    period = rng.uniform(4, 10)
    rows = 0.5 + 0.5 * np.sin(2 * math.pi * u / period)
    tex = 0.6 * rows + 0.4 * (0.5 + 0.25 * _noise(rng, h, w, 1.2) * 3)
    green = np.array([rng.uniform(30, 70), rng.uniform(90, 150), rng.uniform(40, 90)], np.float32)
    bgr = green[None, None, :] * (0.7 + 0.6 * tex[..., None])
    if rng.random() < 0.5:  # tramlines, the tractor paths every field has
        s = rng.uniform(w * 0.3, w * 0.9)
        v = -xx * math.sin(ang) + yy * math.cos(ang)
        bgr[(np.abs((v % s) - s / 2) < 2)] *= 0.75
    return np.clip(bgr, 0, 255).astype(np.uint8)


def apply_medium(canvas: np.ndarray, medium: str, rng: np.random.Generator, backdrops) -> tuple[np.ndarray, bool]:
    """Return (bgr, light_ink)."""
    h, w = canvas.shape
    alpha = (255 - canvas.astype(np.float32)) / 255.0
    if medium in ("pen", "marker"):
        from glyphbyte.synth import composite_ink
        return composite_ink(canvas, random_backdrop(rng, backdrops, h, w), rng)
    if medium == "chalk":
        bd = _pavement(rng, h, w) if (not backdrops or rng.random() < 0.7) else random_backdrop(rng, backdrops, h, w)
        grain = _noise(rng, h, w, rng.uniform(0.5, 1.5))
        keep = np.clip((grain * 3 + rng.uniform(0.3, 1.5)) / 2, 0, 1)   # chalk skips over the texture
        a = alpha * keep * rng.uniform(0.55, 0.95)
        a = np.maximum(a, cv2.GaussianBlur(alpha, (0, 0), 3) * 0.15)     # dust
        col = np.array([rng.uniform(190, 250)] * 3, np.float32) * rng.uniform(0.85, 1.0, 3)
        if rng.random() < 0.3:  # coloured chalk
            col = np.array([rng.uniform(120, 250), rng.uniform(120, 250), rng.uniform(120, 250)], np.float32)
        out = bd.astype(np.float32) * (1 - a[..., None]) + col * a[..., None]
        return np.clip(out, 0, 255).astype(np.uint8), True
    if medium == "crop":
        bd = _field(rng, h, w)
        ragged = cv2.GaussianBlur(alpha, (0, 0), 1.5) + 0.35 * _noise(rng, h, w, 1.0) * 3
        a = np.clip((ragged - 0.35) * 3, 0, 1)
        flat = np.array([rng.uniform(80, 140), rng.uniform(170, 220), rng.uniform(170, 220)], np.float32)
        tex = 0.85 + 0.3 * _noise(rng, h, w, 2)[..., None]
        out = bd.astype(np.float32) * (1 - a[..., None]) + flat * tex * a[..., None]
        return np.clip(out, 0, 255).astype(np.uint8), True
    raise ValueError(medium)


def photo_of_glyph(set_name: str, byte: int, medium: str, rng: np.random.Generator, backdrops,
                   hand: float | None = None):
    """A photographed glyph in the given medium: (gray image, delimiter corners, light_ink)."""
    hand = float(rng.uniform(0.3, 1.0)) if hand is None else hand
    cell = int(rng.integers(110, 190))
    lo, hi = THICKNESS[medium]
    th = cell * rng.uniform(lo, hi)
    canvas, corners = render_glyph(set_name, byte, cell, th, hand, rng)
    bgr, light = apply_medium(canvas, medium, rng, backdrops)
    H, W = bgr.shape[:2]
    persp = rng.uniform(0, 0.3 if medium == "crop" else 0.22)
    Hm = random_homography(rng, W, H, persp)
    ang = rng.uniform(-20, 20)
    Rm = np.vstack([cv2.getRotationMatrix2D((W / 2, H / 2), ang, 1.0), [0, 0, 1]])
    M = Rm @ Hm
    warped = cv2.warpPerspective(bgr, M, (W, H), borderMode=cv2.BORDER_REFLECT)
    # the glyph's size in the photo: 24 px (far away) to full resolution
    target = rng.uniform(24, cell) if rng.random() < 0.5 else cell
    s = target / cell
    if s < 0.98:
        small = cv2.resize(warped, (max(8, int(W * s)), max(8, int(H * s))), interpolation=cv2.INTER_AREA)
        warped = cv2.resize(small, (W, H), interpolation=cv2.INTER_LINEAR)
    warped = photometric(warped, rng, 0.8)
    gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
    q = cv2.perspectiveTransform(corners.reshape(-1, 1, 2).astype(np.float32), M.astype(np.float32)).reshape(4, 2)
    return gray, q, light, cell
