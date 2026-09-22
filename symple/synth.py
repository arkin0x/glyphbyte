"""Synthetic data: classifier training patches and full test scenes on backdrops.

Everything the recognizer will ever see at inference is simulated here:
hand-drawn wobble, ink on textured surfaces or on a paper patch, perspective,
lighting, blur, noise and JPEG. Patches are produced by rendering a cell,
warping it, and rectifying it back with *noisy* frame corners, which is
exactly what the detector does to a real photo.
"""

from __future__ import annotations

import glob
import math
import os
from dataclasses import dataclass, field

import cv2
import numpy as np

from .render import draw_cell, render_row
from .symbols import pack

PATCH = 64            # classifier input size
PATCH_MARGIN = 0.12   # fraction of the frame size kept around the frame in the patch


# ----------------------------------------------------------------------------- backdrops

def load_backdrops(directory: str | None) -> list[np.ndarray]:
    if not directory:
        return []
    files = sorted(glob.glob(os.path.join(directory, "*.jpg")) + glob.glob(os.path.join(directory, "*.png")))
    out = []
    for f in files:
        im = cv2.imread(f, cv2.IMREAD_COLOR)
        if im is not None and im.shape[0] >= 64 and im.shape[1] >= 64:
            out.append(im)
    return out


def procedural_backdrop(rng: np.random.Generator, h: int, w: int) -> np.ndarray:
    """A plausible surface with no photo: paper, wood grain, tiles, concrete, lined paper, dark board."""
    kind = rng.integers(0, 6)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    base = rng.uniform(150, 245)
    if kind == 0:    # paper with gentle gradient
        g = base + (xx / w - 0.5) * rng.uniform(-60, 60) + (yy / h - 0.5) * rng.uniform(-60, 60)
    elif kind == 1:  # wood grain
        ang = rng.uniform(0, math.pi)
        u = xx * math.cos(ang) + yy * math.sin(ang)
        g = base - 40 + 25 * np.sin(u * rng.uniform(0.05, 0.2) + 3 * np.sin(u * 0.01)) + rng.normal(0, 6, (h, w))
    elif kind == 2:  # tiles / bricks
        s = rng.integers(40, 140)
        g = np.full((h, w), base - 20, np.float32)
        g[(xx % s < 3) | (yy % s < 3)] = base - 90
    elif kind == 3:  # concrete speckle
        g = base - 60 + cv2.GaussianBlur(rng.normal(0, 40, (h, w)).astype(np.float32), (0, 0), 2)
    elif kind == 4:  # lined paper
        g = np.full((h, w), base, np.float32)
        g[(yy % rng.integers(24, 48)) < 2] = base - 80
    else:            # dark board (chalk situation, ink will be light)
        g = rng.uniform(20, 70) + cv2.GaussianBlur(rng.normal(0, 12, (h, w)).astype(np.float32), (0, 0), 3)
    g = np.clip(g, 0, 255).astype(np.uint8)
    bgr = cv2.cvtColor(g, cv2.COLOR_GRAY2BGR).astype(np.float32)
    tint = rng.uniform(0.85, 1.15, size=3)
    return np.clip(bgr * tint, 0, 255).astype(np.uint8)


def random_backdrop(rng: np.random.Generator, backdrops: list[np.ndarray], h: int, w: int) -> np.ndarray:
    if backdrops and rng.random() < 0.75:
        im = backdrops[rng.integers(len(backdrops))]
        H, W = im.shape[:2]
        scale = rng.uniform(0.35, 1.0)
        ch, cw = max(h, int(H * scale)), max(w, int(W * scale))
        # random crop of a resized copy
        r = cv2.resize(im, (max(cw, w), max(ch, h)))
        y0 = rng.integers(0, r.shape[0] - h + 1)
        x0 = rng.integers(0, r.shape[1] - w + 1)
        crop = r[y0:y0 + h, x0:x0 + w].copy()
        if rng.random() < 0.5:
            crop = cv2.flip(crop, rng.integers(-1, 2))
        return crop
    return procedural_backdrop(rng, h, w)


# ----------------------------------------------------------------------------- compositing

def composite_ink(canvas: np.ndarray, backdrop: np.ndarray, rng: np.random.Generator,
                  force_paper: bool | None = None) -> tuple[np.ndarray, bool]:
    """Put a rendered ink canvas (white paper, dark ink) onto a backdrop.

    Returns (bgr, light_ink). Either the ink goes straight onto the surface, or the
    canvas becomes a paper/sticker patch on the surface. On dark surfaces the ink
    is light (chalk, paint marker)."""
    h, w = canvas.shape[:2]
    bd = cv2.resize(backdrop, (w, h)).astype(np.float32)
    alpha = (255 - canvas.astype(np.float32)) / 255.0
    alpha = alpha[..., None]
    paper = force_paper if force_paper is not None else rng.random() < 0.35
    if paper:
        paper_col = np.array([rng.uniform(200, 255)] * 3, np.float32) * rng.uniform(0.9, 1.05, size=3)
        pad = 0.04
        mask = np.zeros((h, w), np.float32)
        cv2.rectangle(mask, (int(w * pad), int(h * pad)), (int(w * (1 - pad)), int(h * (1 - pad))), 1.0, -1)
        mask = cv2.GaussianBlur(mask, (0, 0), 1.5)[..., None]
        bd = bd * (1 - mask) + paper_col * mask
    lum = float(bd.mean())
    light_ink = lum < 95 and rng.random() < 0.85
    if light_ink:
        ink_col = np.array([rng.uniform(190, 255)] * 3, np.float32) * rng.uniform(0.85, 1.0, size=3)
    else:
        dark = rng.uniform(0, 70)
        ink_col = np.array([dark, dark, dark], np.float32)
        if rng.random() < 0.4:  # blue / red / green pen
            ink_col = np.array([rng.uniform(0, 160), rng.uniform(0, 90), rng.uniform(0, 90)], np.float32)[rng.permutation(3)]
    # ink density varies a little across the stroke
    density = rng.uniform(0.75, 1.0)
    out = bd * (1 - alpha * density) + ink_col * (alpha * density)
    return np.clip(out, 0, 255).astype(np.uint8), light_ink


def random_homography(rng: np.random.Generator, w: int, h: int, strength: float) -> np.ndarray:
    src = np.array([[0, 0], [w, 0], [w, h], [0, h]], np.float32)
    d = strength * min(w, h)
    dst = src + rng.uniform(-d, d, size=(4, 2)).astype(np.float32)
    # keep it a sane quadrilateral
    dst[:, 0] = np.clip(dst[:, 0], -0.3 * w, 1.3 * w)
    dst[:, 1] = np.clip(dst[:, 1], -0.3 * h, 1.3 * h)
    return cv2.getPerspectiveTransform(src, dst)


def photometric(img: np.ndarray, rng: np.random.Generator, amount: float = 1.0) -> np.ndarray:
    x = img.astype(np.float32)
    h, w = x.shape[:2]
    # lighting gradient and vignette
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    grad = 1 + amount * ((xx / w - 0.5) * rng.uniform(-0.5, 0.5) + (yy / h - 0.5) * rng.uniform(-0.5, 0.5))
    x = x * grad[..., None]
    if rng.random() < 0.5 * amount:  # soft shadow
        mask = np.zeros((h, w), np.float32)
        pts = (rng.uniform(-0.2, 1.2, size=(4, 2)) * [w, h]).astype(np.int32)
        cv2.fillPoly(mask, [pts], 1.0)
        mask = cv2.GaussianBlur(mask, (0, 0), rng.uniform(5, 40))
        x = x * (1 - mask[..., None] * rng.uniform(0.2, 0.55))
    x = x * rng.uniform(1 - 0.35 * amount, 1 + 0.25 * amount) + rng.uniform(-30, 30) * amount
    x = 255 * (np.clip(x, 0, 255) / 255) ** rng.uniform(0.7, 1.4)
    if rng.random() < 0.6 * amount:
        x = cv2.GaussianBlur(x, (0, 0), rng.uniform(0.3, 1.8))
    if rng.random() < 0.25 * amount:  # motion blur
        k = rng.integers(3, 9)
        kern = np.zeros((k, k), np.float32)
        kern[k // 2, :] = 1.0 / k
        M = cv2.getRotationMatrix2D((k / 2 - 0.5, k / 2 - 0.5), rng.uniform(0, 180), 1)
        kern = cv2.warpAffine(kern, M, (k, k))
        kern /= max(kern.sum(), 1e-6)
        x = cv2.filter2D(x, -1, kern)
    x = x + rng.normal(0, rng.uniform(0, 10) * amount, x.shape)
    x = np.clip(x, 0, 255).astype(np.uint8)
    if rng.random() < 0.7 * amount:
        q = int(rng.integers(35, 95))
        ok, enc = cv2.imencode(".jpg", x, [cv2.IMWRITE_JPEG_QUALITY, q])
        if ok:
            x = cv2.imdecode(enc, cv2.IMREAD_COLOR)
    return x


# ----------------------------------------------------------------------------- patches

def normalize_patch(gray: np.ndarray, light_ink: bool = False) -> np.ndarray:
    """Illumination-invariant patch: local mean removed, local contrast normalized,
    ink made dark. Shared by training and inference so the domains match."""
    p = gray.astype(np.float32)
    bg = cv2.GaussianBlur(p, (0, 0), gray.shape[0] / 6)
    d = p - bg
    if light_ink:
        d = -d
    s = np.sqrt(cv2.GaussianBlur(d * d, (0, 0), gray.shape[0] / 4)) + 4.0
    n = np.clip(d / s, -3, 3)
    return ((n + 3) / 6 * 255).astype(np.uint8)


def patch_target_quad(size: int = PATCH, margin: float = PATCH_MARGIN) -> np.ndarray:
    m = size * margin
    return np.array([[m, m], [size - m, m], [size - m, size - m], [m, size - m]], np.float32)


def rectify(gray: np.ndarray, corners: np.ndarray, size: int = PATCH) -> np.ndarray:
    """Warp the quadrilateral `corners` (tl, tr, br, bl) into a size x size patch with margin."""
    H = cv2.getPerspectiveTransform(np.asarray(corners, np.float32), patch_target_quad(size))
    return cv2.warpPerspective(gray, H, (size, size), flags=cv2.INTER_AREA, borderMode=cv2.BORDER_REPLICATE)


@dataclass
class PatchSample:
    image: np.ndarray      # PATCH x PATCH uint8, normalized
    byte: int
    sym_rot: int           # symbol * 4 + rotation
    fill: int
    frame: int


def make_patch(rng: np.random.Generator, backdrops: list[np.ndarray], byte: int | None = None,
               hand: float | None = None) -> PatchSample:
    byte = int(rng.integers(0, 256)) if byte is None else byte
    hand = float(rng.uniform(0.0, 1.0)) if hand is None else hand
    cell = int(rng.integers(90, 200))
    pad = int(cell * 0.45)
    W = H = cell + 2 * pad
    canvas = np.full((H, W), 255, np.uint8)
    thickness = cell * rng.uniform(0.025, 0.08)
    geo = draw_cell(canvas, byte, (W / 2, H / 2), cell, thickness, 0, rng, hand)
    bgr, light_ink = composite_ink(canvas, random_backdrop(rng, backdrops, H, W), rng)
    Hm = random_homography(rng, W, H, rng.uniform(0, 0.22))
    warped = cv2.warpPerspective(bgr, Hm, (W, H), borderMode=cv2.BORDER_REFLECT)
    warped = photometric(warped, rng)
    gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
    corners = cv2.perspectiveTransform(geo.corners.reshape(-1, 1, 2).astype(np.float32), Hm).reshape(4, 2)
    # detector error model: corner noise, plus a scale bias because the detected frame is
    # the ink boundary, not the drawn centerline
    corners += rng.normal(0, 0.035 * cell, size=(4, 2))
    c = corners.mean(axis=0)
    corners = c + (corners - c) * rng.uniform(0.92, 1.12)
    # sometimes the detector's "up" is off by a few degrees
    if rng.random() < 0.5:
        ang = rng.normal(0, math.radians(5))
        R = np.array([[math.cos(ang), -math.sin(ang)], [math.sin(ang), math.cos(ang)]])
        corners = c + (corners - c) @ R.T
    patch = rectify(gray, corners.astype(np.float32))
    patch = normalize_patch(patch, light_ink)
    g = byte
    return PatchSample(image=patch, byte=g, sym_rot=(g >> 4) * 4 + ((g >> 2) & 3), fill=(g >> 1) & 1, frame=g & 1)


# ----------------------------------------------------------------------------- scenes

@dataclass
class Scene:
    image: np.ndarray                     # BGR photo-like image
    data: bytes
    cells: list[dict] = field(default_factory=list)   # {"byte", "corners": 4x2 in scene coords}
    baseline: np.ndarray | None = None    # 2x2 endpoints in scene coords, start first
    light_ink: bool = False
    hand: float = 0.0
    perspective: float = 0.0


def make_scene(rng: np.random.Generator, backdrops: list[np.ndarray], data: bytes | None = None,
               n_bytes: int | None = None, hand: float | None = None, perspective: float | None = None,
               size: int = 1280, baseline: bool = True) -> Scene:
    if data is None:
        n = n_bytes or int(rng.integers(2, 9))
        data = bytes(rng.integers(0, 256, size=n).tolist())
    hand = float(rng.uniform(0.2, 1.0)) if hand is None else hand
    perspective = float(rng.uniform(0.0, 0.2)) if perspective is None else perspective
    cell = int(rng.integers(70, 150))
    row = render_row(data, cell=cell, thickness=cell * rng.uniform(0.03, 0.07), hand=hand, rng=rng,
                     baseline=baseline)
    rh, rw = row.canvas.shape
    # place the row on a larger canvas so the scene has context around it
    W = int(max(rw * rng.uniform(1.1, 1.8), size * 0.6))
    H = int(max(rh * rng.uniform(1.5, 4.0), size * 0.45))
    big = np.full((H, W), 255, np.uint8)
    ox, oy = int(rng.integers(0, W - rw + 1)), int(rng.integers(0, H - rh + 1))
    big[oy:oy + rh, ox:ox + rw] = row.canvas
    bgr, light_ink = composite_ink(big, random_backdrop(rng, backdrops, H, W), rng)
    Hm = random_homography(rng, W, H, perspective)
    # global rotation of the photo: the camera can be held any way
    ang = rng.uniform(-180, 180) if rng.random() < 0.5 else rng.uniform(-15, 15)
    R = cv2.getRotationMatrix2D((W / 2, H / 2), ang, 1.0)
    R3 = np.vstack([R, [0, 0, 1]])
    M = R3 @ Hm
    warped = cv2.warpPerspective(bgr, M, (W, H), borderMode=cv2.BORDER_REFLECT)
    warped = photometric(warped, rng)

    def proj(pts):
        p = np.asarray(pts, np.float32).reshape(-1, 1, 2) + [ox, oy]
        return cv2.perspectiveTransform(p, M.astype(np.float32)).reshape(-1, 2)

    cells = [{"byte": c.byte, "corners": proj(c.corners)} for c in row.cells]
    bl = proj(np.array(row.baseline)) if row.baseline else None
    return Scene(image=warped, data=data, cells=cells, baseline=bl, light_ink=light_ink,
                 hand=hand, perspective=perspective)
