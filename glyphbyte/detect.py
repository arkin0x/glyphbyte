"""Find the row in a photo: framed cells, the baseline and its start dot, then
rectify every cell into a classifier patch.

Pipeline
  1. gray, downscale to at most MAX_SIDE
  2. binarize twice (dark ink, light ink) with a local threshold; keep the polarity
     that yields more frames
  3. frames = ink rings whose hole contains ink; square vs circle by the area of
     the largest quadrilateral inscribed in the hole's hull (1.0 for a quad, 2/pi
     for an ellipse, and perspective does not change either)
  4. baseline = the long thin component next to the frames; start dot = a blob at
     one end, or the end that is thicker than the line
  5. rectify: squares by homography from their four corners, circles by an affine
     map of the fitted ellipse; "up" and reading order come from the baseline
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field

import cv2
import numpy as np

from .symbols import FRAME_CIRCLE, FRAME_SQUARE
from .synth import PATCH, normalize_patch, patch_target_quad, rectify

MAX_SIDE = 1600
JUNK_TOP_K = 24      # candidates offered to the classifier's junk check
_DEBUG = bool(__import__("os").environ.get("GLYPHBYTE_DEBUG"))


@dataclass
class Frame:
    kind: int
    center: np.ndarray
    size: float
    outer: np.ndarray
    hole: np.ndarray
    corners: np.ndarray | None = None        # 4x2 unordered, squares only
    ellipse: tuple | None = None             # ((cx, cy), (MA, ma), angle), circles only
    ink_fraction: float = 0.0
    quad_ratio: float = 0.0        # confidence of the square/circle decision, 0..1
    stroke: float = 0.0
    quality: float = 1.0           # how much this looks like a drawn frame with a glyph in it
    light_ink: bool = False        # polarity this frame was found in
    junk: float = 0.0              # classifier's probability that this is not a symbol


@dataclass
class Detection:
    frames: list[Frame]
    baseline: np.ndarray | None
    start_known: bool
    up: np.ndarray
    direction: np.ndarray
    light_ink: bool
    scale: float
    gray: np.ndarray
    ink: np.ndarray
    warnings: list[str] = field(default_factory=list)
    patches: list[np.ndarray] = field(default_factory=list)


# ----------------------------------------------------------------------------- basics

def prepare(image: np.ndarray) -> tuple[np.ndarray, float]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image.copy()
    s = 1.0
    m = max(gray.shape)
    if m > MAX_SIDE:
        s = MAX_SIDE / m
        gray = cv2.resize(gray, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    return gray, s


def binarize(gray: np.ndarray, light_ink: bool) -> np.ndarray:
    src = 255 - gray if light_ink else gray
    side = min(gray.shape)
    block = max(31, (side // 14) | 1)
    ink = cv2.adaptiveThreshold(src, 1, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, block, 10)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    ink = cv2.morphologyEx(ink, cv2.MORPH_CLOSE, k)
    # drop specks
    n, lab, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    min_area = max(6, (side / 250) ** 2)
    keep = np.zeros(n, bool)
    keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= min_area
    return keep[lab].astype(np.uint8)


def max_inscribed_quad(hull: np.ndarray) -> tuple[np.ndarray | None, float]:
    """Largest-area quadrilateral with vertices on the (simplified) hull, and its area."""
    peri = cv2.arcLength(hull.reshape(-1, 1, 2), True)
    pts = cv2.approxPolyDP(hull.reshape(-1, 1, 2), 0.012 * peri, True).reshape(-1, 2).astype(np.float64)
    if len(pts) > 14:
        idx = np.linspace(0, len(pts) - 1, 14).astype(int)
        pts = pts[idx]
    if len(pts) < 4:
        return None, 0.0
    combos = np.array(list(itertools.combinations(range(len(pts)), 4)))
    q = pts[combos]                                   # K x 4 x 2, vertices in hull order
    x, y = q[..., 0], q[..., 1]
    area = 0.5 * np.abs((x * np.roll(y, -1, axis=1)).sum(axis=1) - (y * np.roll(x, -1, axis=1)).sum(axis=1))
    k = int(np.argmax(area))
    return q[k], float(area[k])


# ----------------------------------------------------------------------------- frames

def _ray_stroke(ink: np.ndarray, region: np.ndarray, center: np.ndarray, size: float, n_rays: int = 16) -> float:
    """Median ink run length just outside `region` along rays from its center: the
    thickness of the ring around it. A thin stroke gives a small number; the paper
    interior of a frame seen in inverted polarity gives a fat one."""
    h, w = ink.shape
    limit = int(max(4, 0.35 * size))
    slack_max = int(max(2, 0.08 * size))   # background allowed between the region's edge and the stroke
    runs = []
    for k in range(n_rays):
        a = 2 * math.pi * k / n_rays
        dx, dy = math.cos(a), math.sin(a)
        x, y = float(center[0]), float(center[1])
        inside = True
        run = 0
        slack = 0
        for _ in range(int(0.9 * size) + limit + slack_max):
            x += dx
            y += dy
            xi, yi = int(round(x)), int(round(y))
            if not (0 <= xi < w and 0 <= yi < h):
                break
            if inside:
                if region[yi, xi]:
                    continue
                inside = False
            if ink[yi, xi]:
                run += 1
                if run > limit:
                    break
            elif run > 0:
                break
            else:
                slack += 1
                if slack > slack_max:
                    break   # a real gap in the ring along this ray
        runs.append(run)
    runs = [r for r in runs if r > 0]
    if len(runs) < n_rays // 2:
        return 0.0
    return float(np.median(runs))


def _classify_kind(hull: np.ndarray) -> tuple[int, float, np.ndarray | None]:
    """(kind, confidence 0..1, quad). Ratio of the largest inscribed quad to the hull area is
    ~1 for a quadrilateral and 2/pi for an ellipse, in any perspective."""
    quad, qarea = max_inscribed_quad(hull)
    hull_area = cv2.contourArea(hull.reshape(-1, 1, 2))
    ratio = qarea / max(hull_area, 1e-6)
    peri = cv2.arcLength(hull.reshape(-1, 1, 2), True)
    nv = len(cv2.approxPolyDP(hull.reshape(-1, 1, 2), 0.02 * peri, True))
    score = (ratio - 0.80) / 0.06 + (5.5 - nv) / 3.0      # >0 square, <0 circle
    kind = FRAME_SQUARE if score > 0 else FRAME_CIRCLE
    conf = float(min(1.0, abs(score) / 1.5))
    return kind, conf, quad


def find_frames(ink: np.ndarray) -> list[Frame]:
    h, w = ink.shape
    side = min(h, w)
    min_size, max_size = side / 45.0, side / 1.15
    cnts, hier = cv2.findContours(ink, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if hier is None:
        return []
    hier = hier[0]
    out: list[Frame] = []

    def consider(region: np.ndarray, size_hint: float, ring_outer: np.ndarray | None):
        x, y, bw, bh = cv2.boundingRect(region)
        if max(bw, bh) < min_size or max(bw, bh) > max_size:
            return
        if max(bw, bh) / max(1, min(bw, bh)) > 2.2:
            return
        area = cv2.contourArea(region)
        if area < 20:
            return
        pad = int(0.5 * max(bw, bh)) + 4
        x0, y0 = max(0, x - pad), max(0, y - pad)
        x1, y1 = min(w, x + bw + pad), min(h, y + bh + pad)
        ink_roi = ink[y0:y1, x0:x1]
        # the interior is the hull of the hole: a glyph that touches the frame bites into
        # the hole, and the hull fills it back in so the centre and the rays stay honest
        hull = cv2.convexHull(region).reshape(-1, 2)
        hull_area = cv2.contourArea(hull.reshape(-1, 1, 2))
        if hull_area <= 0 or area / hull_area < 0.35:
            return
        mask = np.zeros_like(ink_roi)
        cv2.fillPoly(mask, [hull.reshape(-1, 1, 2) - [x0, y0]], 1)
        px = int(mask.sum())
        if px < 20:
            return
        frac = float((ink_roi & mask).sum()) / px
        if frac < 0.015 or frac > 0.75:
            return
        size = math.sqrt(px)
        M = cv2.moments(hull.reshape(-1, 1, 2))
        center = np.array([M["m10"] / M["m00"], M["m01"] / M["m00"]]) if M["m00"] else np.array([x + bw / 2.0, y + bh / 2.0])
        stroke = _ray_stroke(ink_roi, mask, center - [x0, y0], size)
        if stroke < 1.0 or stroke > 0.16 * size:
            return
        kind, conf, quad = _classify_kind(hull)
        # quality: a drawn frame has a thin stroke, a moderate amount of ink inside, and that
        # ink sits in the middle. backdrop holes fail one or more of these.
        inside = (ink_roi & mask)
        ys, xs = np.nonzero(inside)
        if len(xs):
            off_c = np.hypot(xs.mean() + x0 - center[0], ys.mean() + y0 - center[1]) / size
        else:
            off_c = 1.0
        # a glyph is one blob (two for an outline with an inner loop); texture is confetti
        n_cc, _, cc_stats, _ = cv2.connectedComponentsWithStats(inside.astype(np.uint8), connectivity=8)
        share = float(cc_stats[1:, cv2.CC_STAT_AREA].max()) / max(1, int(inside.sum())) if n_cc > 1 else 0.0
        q = 1.0
        q *= 1.0 if 0.04 <= frac <= 0.5 else 0.5
        q *= 1.0 if 0.02 <= stroke / size <= 0.10 else 0.5
        q *= 0.5 + 0.5 * conf
        q *= 1.0 if off_c <= 0.22 else 0.5
        q *= 1.0 if share >= 0.5 else (0.6 if share >= 0.3 else 0.3)
        if kind == FRAME_CIRCLE:
            size = math.sqrt(px / math.pi) * 2
        fr = Frame(kind=kind, center=center, size=size, outer=ring_outer if ring_outer is not None else hull,
                   hole=region.reshape(-1, 2), ink_fraction=frac, quad_ratio=conf, stroke=stroke, quality=q)
        if kind == FRAME_SQUARE and quad is not None:
            fr.corners = center + (quad - center) * (1 + 0.5 * stroke / max(size, 1))
        if len(region) >= 5:
            (cx, cy), (MA, ma), ang = cv2.fitEllipse(region)
            fr.ellipse = ((cx, cy), (MA + stroke, ma + stroke), ang)
        out.append(fr)

    # A) holes: a frame's interior survives even when the ring merged with other ink
    for i, c in enumerate(cnts):
        if hier[i][3] == -1:
            continue
        consider(c, 0.0, None)
    # B) rings with a pen gap: an external contour with low solidity whose hull encloses other ink
    for i, c in enumerate(cnts):
        if hier[i][3] != -1:
            continue
        x, y, bw, bh = cv2.boundingRect(c)
        if max(bw, bh) < min_size or max(bw, bh) > max_size:
            continue
        hull = cv2.convexHull(c)
        ha = cv2.contourArea(hull)
        if ha <= 0 or cv2.contourArea(c) / ha > 0.5:
            continue
        # the region is the hull minus this component's own ink
        comp = np.zeros((h, w), np.uint8)
        cv2.drawContours(comp, [c], -1, 1, -1)
        inner = np.zeros((h, w), np.uint8)
        cv2.fillPoly(inner, [hull], 1)
        k = max(3, int(0.03 * max(bw, bh)) | 1)
        inner = cv2.erode(inner & (1 - comp), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
        ic, _ = cv2.findContours(inner, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not ic:
            continue
        region = max(ic, key=cv2.contourArea)
        consider(region, 0.0, c.reshape(-1, 2))

    # dedupe: same frame seen twice, or a glyph ring inside a frame
    out.sort(key=lambda f: -f.size)
    keep: list[Frame] = []
    for f in out:
        dup = False
        for g in keep:
            if np.linalg.norm(f.center - g.center) < 0.35 * g.size and f.size < 1.3 * g.size:
                dup = True
                break
            # a ring inside a frame at glyph scale is the glyph (u, crescent, pacman...), unless
            # the "frame" around it is a poor one (a paper patch, a tile) and this is the real thing
            if (0.3 * g.size < f.size < 0.8 * g.size and g.quality >= 0.7 * f.quality
                    and cv2.pointPolygonTest(g.hole.reshape(-1, 1, 2).astype(np.float32), tuple(map(float, f.center)), False) >= 0):
                dup = True
                break
        if not dup:
            keep.append(f)
    return keep


def filter_row(frames: list[Frame]) -> tuple[list[Frame], list[str]]:
    """Keep the largest set of frames that share a size and a line: the row.
    Anything else is backdrop texture that happened to look like a frame."""
    warnings = []
    if len(frames) <= 1:
        return frames, warnings
    best: list[int] = []
    n = len(frames)
    pts = np.array([f.center for f in frames])
    sizes = np.array([f.size for f in frames])
    quality = np.array([f.quality for f in frames])
    pairs = [(i, j) for i in range(n) for j in range(i + 1, n)]
    for i, j in pairs:
        s_ref = (sizes[i] + sizes[j]) / 2
        if not (0.6 <= sizes[i] / sizes[j] <= 1.67):
            continue
        d = pts[j] - pts[i]
        L = np.linalg.norm(d)
        if L < 0.8 * s_ref:
            continue
        d /= L
        nrm = np.array([-d[1], d[0]])
        off = np.abs((pts - pts[i]) @ nrm)
        # perspective makes cells shrink along the row, so the size window is wide here and
        # a smooth size trend is enforced below
        ok = [k for k in range(n) if off[k] <= 0.45 * s_ref and 0.4 <= sizes[k] / s_ref <= 2.5]
        ok.sort(key=lambda k: float((pts[k] - pts[i]) @ d))
        if len(ok) >= 3:
            t = np.array([float((pts[k] - pts[i]) @ d) for k in ok])
            sz = sizes[ok]
            coef = np.polyfit(t, sz, 1)
            trend = np.polyval(coef, t)
            ok = [k for k, a, b in zip(ok, sz, trend) if 0.65 <= a / max(b, 1e-6) <= 1.5]
        # frames in a row do not overlap: enforce a minimum spacing along the line
        spaced = []
        for k in ok:
            if not spaced or float((pts[k] - pts[spaced[-1]]) @ d) >= 0.8 * min(sizes[k], sizes[spaced[-1]]):
                spaced.append(k)
        if quality[spaced].sum() > quality[best].sum() + 1e-9:
            best = spaced
    if len(best) < 2:
        best = [int(np.argmax(quality * (1 + 0.001 * sizes)))]
    if len(best) < n:
        warnings.append(f"dropped {n - len(best)} frame(s) that were not on the row")
    return [frames[k] for k in best], warnings


# ----------------------------------------------------------------------------- baseline

def _row_axis(frames: list[Frame]) -> np.ndarray:
    pts = np.array([f.center for f in frames])
    if len(pts) >= 2:
        _, _, vt = np.linalg.svd(pts - pts.mean(axis=0))
        d = vt[0]
    else:
        d = np.array([1.0, 0.0])
    return d / np.linalg.norm(d)


def _sample_line(ink_d: np.ndarray, p0: np.ndarray, d: np.ndarray, t0: float, t1: float, step: float = 1.0):
    ts = np.arange(t0, t1, step)
    pts = p0[None, :] + ts[:, None] * d[None, :]
    xs = np.round(pts[:, 0]).astype(int)
    ys = np.round(pts[:, 1]).astype(int)
    ok = (xs >= 0) & (ys >= 0) & (xs < ink_d.shape[1]) & (ys < ink_d.shape[0])
    hit = np.zeros(len(ts), bool)
    hit[ok] = ink_d[ys[ok], xs[ok]] > 0
    return ts, hit


def _sample_band(ink, p0, d, nrm, t0, t1, tol):
    """Like _sample_line, but a step counts as a hit when any ink lies within tol pixels
    perpendicular to the line: a hand-drawn underline sags and rises."""
    ts = np.arange(t0, t1, 1.0)
    hit = np.zeros(len(ts), bool)
    offs = np.arange(-tol, tol + 1)
    for i, t in enumerate(ts):
        cx, cy = p0[0] + d[0] * t, p0[1] + d[1] * t
        xs = np.round(cx + nrm[0] * offs).astype(int)
        ys = np.round(cy + nrm[1] * offs).astype(int)
        ok = (xs >= 0) & (ys >= 0) & (xs < ink.shape[1]) & (ys < ink.shape[0])
        if ok.any() and ink[ys[ok], xs[ok]].any():
            hit[i] = True
    return ts, hit


def _refine_line(ink, ink_d, ink_lines, p0, d, nrm, med, t_lo, t_hi):
    """Least-squares fit to the ink in a thin band around a candidate line, then its extent.
    Returns (pa, pb, d, nrm) or None."""
    ts, hit = _sample_line(ink_d, p0, d, t_lo, t_hi)
    band = int(max(3, 0.12 * med))   # hand-drawn lines sag and rise; gather generously before fitting
    pts = []
    for t in ts[hit]:
        c = p0 + d * t
        for o in range(-band, band + 1):
            q = c + nrm * o
            x, y = int(round(q[0])), int(round(q[1]))
            if 0 <= y < ink.shape[0] and 0 <= x < ink.shape[1] and ink[y, x]:
                pts.append((x, y))
    if len(pts) >= 10:
        pts = np.array(pts, np.float64)
        c = pts.mean(axis=0)
        cov = np.cov((pts - c).T)
        evals, evecs = np.linalg.eigh(cov)
        d2 = evecs[:, int(np.argmax(evals))]
        if d2 @ d < 0:
            d2 = -d2
        d, p0 = d2, c
        nrm = np.array([-d[1], d[0]])
    ts, hit = _sample_band(ink_lines, p0, d, nrm, t_lo - med, t_hi + med, max(3, int(0.1 * med)))
    idx = np.nonzero(hit)[0]
    if len(idx) == 0:
        return None
    gap = 0.5 * med
    runs, start = [], idx[0]
    for i, j in zip(idx[:-1], idx[1:]):
        if ts[j] - ts[i] > gap:
            runs.append((start, i))
            start = j
    runs.append((start, idx[-1]))
    r0, r1 = max(runs, key=lambda r: ts[r[1]] - ts[r[0]])
    pa, pb = p0 + d * ts[r0], p0 + d * ts[r1]
    if np.linalg.norm(pb - pa) < 1.2 * med:
        return None
    return pa, pb, d, nrm


def _fill_small_holes(ink: np.ndarray, max_area: float) -> np.ndarray:
    """The local threshold hollows out filled blobs wider than its window (the start dot,
    filled glyphs). Filling holes below max_area restores them; frame interiors stay."""
    cnts, hier = cv2.findContours(ink, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    out = ink.copy()
    if hier is None:
        return out
    small = [c for c, h in zip(cnts, hier[0]) if h[3] != -1 and cv2.contourArea(c) < max_area]
    if small:
        cv2.fillPoly(out, small, 1)
    return out


def _dot_evidence(ink, dist, pa, pb, med):
    """(start_index 0|1 or None, strength). The start dot makes one end of the line much
    thicker than the line itself."""
    ink = _fill_small_holes(ink, (0.35 * med) ** 2)
    dist = cv2.distanceTransform(ink, cv2.DIST_L2, 3)

    def thickness_near(p, radius):
        x, y = int(round(p[0])), int(round(p[1]))
        r = int(radius)
        y0, y1 = max(0, y - r), min(ink.shape[0], y + r + 1)
        x0, x1 = max(0, x - r), min(ink.shape[1], x + r + 1)
        return float(dist[y0:y1, x0:x1].max()) if y1 > y0 and x1 > x0 else 0.0

    def roundness_near(p, radius):
        """ink area around the thickest point over the disc area that thickness implies:
        about 1 for a dot (plus a bit of line), well above 2 for crossing strokes."""
        x, y = int(round(p[0])), int(round(p[1]))
        r = int(radius)
        y0, y1 = max(0, y - r), min(ink.shape[0], y + r + 1)
        x0, x1 = max(0, x - r), min(ink.shape[1], x + r + 1)
        win = dist[y0:y1, x0:x1]
        if win.size == 0 or win.max() <= 0:
            return 9.0
        iy, ix = np.unravel_index(int(win.argmax()), win.shape)
        rr = float(win.max())
        k = int(1.6 * rr) + 1
        cy, cx = y0 + iy, x0 + ix
        blob = ink[max(0, cy - k):cy + k + 1, max(0, cx - k):cx + k + 1]
        return float(blob.sum()) / max(1.0, math.pi * rr * rr)

    mids = [thickness_near(pa + (pb - pa) * t, max(2, 0.04 * med)) for t in np.linspace(0.25, 0.75, 9)]
    line_half = max(1.0, float(np.median(mids)))
    L = max(1e-6, float(np.linalg.norm(pb - pa)))
    u = (pb - pa) / L

    def end_scan(p, direction, reach):
        """fattest spot within `reach` med of an end, scanning inward"""
        best, best_p = 0.0, p
        for t in np.arange(-0.15 * med, reach * med, max(1.0, 0.05 * med)):
            q = p + direction * t
            if not (0 <= q[0] < ink.shape[1] and 0 <= q[1] < ink.shape[0]):
                continue  # the photo's border is not a dot
            v = thickness_near(q, max(2, 0.12 * med))
            if v > best:
                best, best_p = v, q
        return best, best_p

    # the dot may sit well inside the run's end (paper grain and the paper's own edge can
    # carry the run past it), so it is sought up to 0.9 med in; the other end is judged thin
    # or fat within 0.4 med only, or a glyph near that end would look like a second dot
    ta, qa = end_scan(pa, u, 0.9)
    tb, qb = end_scan(pb, -u, 0.9)
    a_fat = ta > tb
    near = end_scan(pb, -u, 0.4)[0] if a_fat else end_scan(pa, u, 0.4)[0]
    hi, lo = (ta if a_fat else tb) / line_half, near / line_half
    ra, rb = (hi, lo) if a_fat else (lo, hi)
    fat = qa if a_fat else qb
    rd = roundness_near(fat, 0.12 * med)
    if _DEBUG:
        print("[baseline] line_half", round(line_half, 2), "ratio a", round(ra, 2), "b", round(rb, 2), "roundness", round(rd, 2))
    # a start dot is one fat, round end and one thin end; texture is fat at both ends
    if hi >= 1.8 and lo <= 1.6 and hi >= 1.5 * lo and rd <= 3.5:
        return (0 if a_fat else 1), hi
    return None, hi


def find_baseline(ink: np.ndarray, frames: list[Frame]):
    """Returns (p_start, p_end, start_known, up) or None.

    The baseline is a long stroke parallel to the row, just outside it. Every parallel
    offset is scored by ink coverage in the gaps between frames and beyond the row's
    ends (where the frames' own edges cannot score); each coverage peak is refined and
    checked for a start dot. The winner has a dot if any does, then the best coverage,
    then the shortest distance to the row: lined paper and tile grids lose on the dot."""
    if not frames:
        return None
    med = float(np.median([f.size for f in frames]))
    centers = np.array([f.center for f in frames])
    m = centers.mean(axis=0)
    d = _row_axis(frames)
    nrm = np.array([-d[1], d[0]])
    along = (centers - m) @ d
    order = np.argsort(along)
    along = along[order]
    sizes = np.array([frames[i].size for i in order])
    # ink that is not part of any frame: the frames' rings are masked out so their edges
    # cannot pose as a baseline, and the underline is scored along the whole row, not just
    # in the gaps between frames (real rows are often drawn with almost no gaps)
    frame_mask = np.zeros_like(ink)
    for f in frames:
        cv2.fillPoly(frame_mask, [f.hole.reshape(-1, 1, 2).astype(np.int32)], 1)
        cv2.fillPoly(frame_mask, [cv2.convexHull(f.outer.reshape(-1, 1, 2).astype(np.int32))], 1)
    kd = max(3, int(2.0 * float(np.median([f.stroke for f in frames])) + 4) | 1)
    frame_mask = cv2.dilate(frame_mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kd, kd)))
    ink_lines = ink & (1 - frame_mask)
    t_lo, t_hi = along[0] - 0.6 * med, along[-1] + 0.6 * med
    ink_d = cv2.dilate(ink_lines, np.ones((5, 5), np.uint8))
    offs, covs = [], []
    for off in np.linspace(-2.4 * med, 2.4 * med, int(4.8 * med / 2) + 1):
        if abs(off) < 0.5 * med:
            continue
        p0 = m + nrm * off
        ts, hit = _sample_line(ink_d, p0, d, t_lo, t_hi)
        if len(ts) < 4:
            continue
        offs.append(off)
        covs.append(float(hit.mean()))
    if not offs:
        return None
    offs, covs = np.array(offs), np.array(covs)
    # local maxima of coverage
    cands = []
    for i in range(len(offs)):
        if covs[i] < 0.3:
            continue
        lo_, hi_ = max(0, i - 3), min(len(offs), i + 4)
        if covs[i] >= covs[lo_:hi_].max():
            if cands and abs(offs[i] - cands[-1][0]) < 0.2 * med:
                if covs[i] > cands[-1][1]:
                    cands[-1] = (offs[i], covs[i])
                continue
            cands.append((offs[i], covs[i]))
    if not cands:
        return None
    dist = cv2.distanceTransform(ink, cv2.DIST_L2, 3)
    scored = []
    for off, cov in cands:
        r = _refine_line(ink, ink_d, ink_lines, m + nrm * off, d, nrm, med, t_lo, t_hi)
        if r is None:
            continue
        pa, pb, d2, nrm2 = r
        start, strength = _dot_evidence(ink_lines, dist, pa, pb, med)
        near = 0.5 <= abs(off) / med <= 1.5       # where an underline actually sits
        # a near line with a start dot beats everything; then a nearly continuous line beats a
        # patchy one (texture), then proximity, then coverage
        scored.append(((near, start is not None, cov >= 0.7, -round(abs(off) / med, 1), cov), off, cov, pa, pb, d2, nrm2, start))
    if not scored:
        return None
    scored.sort(key=lambda t: t[0], reverse=True)
    _, off, cov, pa, pb, d, nrm, start = scored[0]
    side = float(np.sign(((centers - pa) @ nrm).mean()))
    up = nrm * side  # from the line toward the frames
    if _DEBUG:
        print("[baseline] candidates", [(round(float(o), 1), round(float(c), 2)) for o, c in cands], "chosen off", round(float(off), 1), "start", start)
    if start == 0:
        return pa, pb, True, up
    if start == 1:
        return pb, pa, True, up
    if d[0] < 0 or (d[0] == 0 and d[1] < 0):
        pa, pb = pb, pa
    return pa, pb, False, up


# ----------------------------------------------------------------------------- rectification

def order_corners(corners: np.ndarray, center: np.ndarray, d: np.ndarray, up: np.ndarray) -> np.ndarray:
    rel = corners - center
    u, v = rel @ d, rel @ up
    scores = np.stack([-u + v, u + v, u - v, -u - v], axis=1)  # tl, tr, br, bl
    order = []
    taken = set()
    for k in range(4):
        cand = [(scores[i, k], i) for i in range(4) if i not in taken]
        _, i = max(cand)
        order.append(i)
        taken.add(i)
    return corners[order].astype(np.float32)


def circle_matrix(ellipse, d: np.ndarray, size: int = PATCH) -> np.ndarray:
    (cx, cy), (MA, ma), ang = ellipse
    a = math.radians(ang)
    T = np.array([[1, 0, -cx], [0, 1, -cy], [0, 0, 1]])
    R = np.array([[math.cos(-a), -math.sin(-a), 0], [math.sin(-a), math.cos(-a), 0], [0, 0, 1]])
    S = np.diag([2.0 / max(MA, 1e-6), 2.0 / max(ma, 1e-6), 1.0])
    N = S @ R @ T
    dd = N[:2, :2] @ d
    th = math.atan2(dd[1], dd[0])
    R2 = np.array([[math.cos(-th), -math.sin(-th), 0], [math.sin(-th), math.cos(-th), 0], [0, 0, 1]])
    N = R2 @ N
    src = np.array([[-1, -1], [1, -1], [1, 1], [-1, 1]], np.float32)
    P = cv2.getPerspectiveTransform(src, patch_target_quad(size))
    return P @ N


def rectify_frame(gray: np.ndarray, f: Frame, d: np.ndarray, up: np.ndarray, light_ink: bool) -> np.ndarray:
    if f.kind == FRAME_SQUARE and f.corners is not None:
        patch = rectify(gray, order_corners(f.corners, f.center, d, up))
    elif f.ellipse is not None:
        M = circle_matrix(f.ellipse, d)
        patch = cv2.warpPerspective(gray, M.astype(np.float64), (PATCH, PATCH), flags=cv2.INTER_AREA,
                                    borderMode=cv2.BORDER_REPLICATE)
        # ellipse normalisation may mirror; fix handedness so "up" is up (negative y)
        uu = M[:2, :2] @ up
        if uu[1] > 0:
            patch = cv2.flip(patch, 0)
    else:
        h = f.size / 2
        corners = f.center + np.array([[-h, -h], [h, -h], [h, h], [-h, h]])
        patch = rectify(gray, order_corners(corners, f.center, d, up))
    return normalize_patch(patch, light_ink)


# ----------------------------------------------------------------------------- entry

def detect(image: np.ndarray, junk_fn=None) -> Detection:
    """junk_fn(list of patches) -> array of probabilities that each patch is not a symbol.
    When given, candidates are scored by it before the row is chosen, so texture that
    looks like a frame geometrically does not get to outvote the real row."""
    gray, scale = prepare(image)
    # frames from both polarities go into one pool; the row then decides which polarity
    # the drawing has. strokes are sparse, so a polarity that inks most of the picture
    # has binarized the paper and its frames are penalized.
    inks = {}
    pool: list[Frame] = []
    for light in (False, True):
        ink = binarize(gray, light)
        inks[light] = ink
        coverage = float(ink.mean())
        penalty = 1.0 - min(0.9, 3.0 * max(0.0, coverage - 0.2))
        for f in find_frames(ink):
            f.light_ink = light
            f.quality *= penalty
            pool.append(f)
    pool.sort(key=lambda f: -f.quality)
    merged: list[Frame] = []
    for f in pool:
        if any(np.linalg.norm(f.center - g.center) < 0.35 * g.size and 0.6 < f.size / g.size < 1.6 for g in merged):
            continue
        merged.append(f)
    if junk_fn is not None and merged:
        # provisional rectification with the image axes: junk is junk in any rotation.
        # only the best-looking candidates are worth the network's time (the same cap
        # keeps the JavaScript port usable on a phone)
        merged = merged[:JUNK_TOP_K]
        provisional = [rectify_frame(gray, f, np.array([1.0, 0.0]), np.array([0.0, -1.0]), f.light_ink) for f in merged]
        p_junk = np.asarray(junk_fn(provisional), dtype=np.float64)
        for f, pj in zip(merged, p_junk):
            f.junk = float(pj)
            f.quality *= max(0.05, 1.0 - float(pj))
        merged = [f for f in merged if f.junk < 0.9]
    frames, warnings = filter_row(merged)
    votes = sum(1 if f.light_ink else -1 for f in frames)
    light_ink = votes > 0
    ink = inks[light_ink]

    up = np.array([0.0, -1.0])
    d = np.array([1.0, 0.0])
    baseline = None
    start_known = False
    bl = find_baseline(ink, frames)
    if bl is not None:
        p_start, p_end, start_known, up = bl
        d = (p_end - p_start) / max(1e-6, np.linalg.norm(p_end - p_start))
        baseline = np.stack([p_start, p_end])
        if not start_known:
            warnings.append("baseline found but no start dot: reading left to right")
    else:
        warnings.append("no baseline: assuming the photo is upright and reads left to right")

    if frames:
        if bl is not None:
            # frames must sit over the baseline; anything beyond its ends is backdrop
            med = float(np.median([f.size for f in frames]))
            length = float(np.linalg.norm(baseline[1] - baseline[0]))
            proj = [float((f.center - baseline[0]) @ d) for f in frames]
            span = max(proj) - min(proj) if len(proj) > 1 else 0.0
            kept = frames
            if length >= 0.8 * span:   # only trust the extent when the line really spans the row
                kept = [f for f, t in zip(frames, proj) if -0.8 * med <= t <= length + 0.8 * med]
            if kept and len(kept) < len(frames):
                warnings.append(f"dropped {len(frames) - len(kept)} frame(s) beyond the baseline")
                frames = kept
            frames.sort(key=lambda f: float((f.center - baseline[0]) @ d))
        else:
            frames.sort(key=lambda f: float(f.center @ d))
    patches = [rectify_frame(gray, f, d, up, light_ink) for f in frames]
    return Detection(frames=frames, baseline=baseline, start_known=start_known, up=up, direction=d,
                     light_ink=light_ink, scale=scale, gray=gray, ink=ink, warnings=warnings, patches=patches)


def draw_debug(det: Detection) -> np.ndarray:
    vis = cv2.cvtColor(det.gray, cv2.COLOR_GRAY2BGR)
    for i, f in enumerate(det.frames):
        col = (0, 200, 0) if f.kind == FRAME_SQUARE else (255, 128, 0)
        cv2.polylines(vis, [f.hole.reshape(-1, 1, 2).astype(np.int32)], True, col, 2)
        if f.corners is not None:
            for c in f.corners:
                cv2.circle(vis, tuple(np.round(c).astype(int)), 4, (0, 0, 255), -1)
        cv2.putText(vis, str(i), tuple(np.round(f.center).astype(int)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
    if det.baseline is not None:
        p0, p1 = det.baseline
        cv2.line(vis, tuple(np.round(p0).astype(int)), tuple(np.round(p1).astype(int)), (255, 0, 255), 2)
        cv2.circle(vis, tuple(np.round(p0).astype(int)), 8, (255, 0, 255), 2 if det.start_known else 1)
        mid = (p0 + p1) / 2
        cv2.arrowedLine(vis, tuple(np.round(mid).astype(int)), tuple(np.round(mid + det.up * 40).astype(int)), (0, 255, 255), 2)
    return vis
