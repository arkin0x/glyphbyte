"""Render glyphbyte glyphs, frames and rows, either clean or in a hand-drawn style.

Coordinates are image coordinates (y down). Rotation r in quarter turns is
clockwise on screen. Canvases are uint8 grayscale, white paper, dark ink.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import cv2
import numpy as np

from .symbols import FRAME_CIRCLE, Glyph, unpack, load_canonical, pack

_SHAPES: list[dict] | None = None


def shapes() -> list[dict]:
    global _SHAPES
    if _SHAPES is None:
        raw = load_canonical()
        _SHAPES = [
            {"name": s["name"], "outer": np.asarray(s["outer"], dtype=np.float64),
             "features": [np.asarray(f, dtype=np.float64) for f in s["features"]]}
            for s in raw
        ]
    return _SHAPES


# ----------------------------------------------------------------------------- geometry

def rot_matrix(theta: float) -> np.ndarray:
    c, s = math.cos(theta), math.sin(theta)
    return np.array([[c, -s], [s, c]])


def perturb(points: np.ndarray, rng: np.random.Generator, amount: float) -> np.ndarray:
    """Hand-drawn wobble on a closed polygon in unit coordinates.

    Low-frequency sinusoidal displacement along the path plus a little smoothed
    jitter, then a small random anisotropic scale, shear and rotation. amount=0
    returns the input unchanged.
    """
    if amount <= 0:
        return points
    n = len(points)
    t = np.linspace(0, 1, n, endpoint=False)
    disp = np.zeros((n, 2))
    for _ in range(3):
        f = rng.integers(1, 5)
        phase = rng.uniform(0, 2 * math.pi, size=2)
        amp = rng.uniform(0, 0.03) * amount
        disp[:, 0] += amp * np.sin(2 * math.pi * f * t + phase[0])
        disp[:, 1] += amp * np.sin(2 * math.pi * f * t + phase[1])
    jitter = rng.normal(0, 0.006 * amount, size=(n, 2))
    k = np.ones(5) / 5.0
    jitter[:, 0] = np.convolve(np.tile(jitter[:, 0], 3), k, mode="same")[n:2 * n]
    jitter[:, 1] = np.convolve(np.tile(jitter[:, 1], 3), k, mode="same")[n:2 * n]
    p = points + disp + jitter
    sx, sy = 1 + rng.normal(0, 0.07 * amount, size=2)
    shear = rng.normal(0, 0.07 * amount)
    theta = rng.normal(0, math.radians(6) * amount)
    A = rot_matrix(theta) @ np.array([[sx, shear], [0, sy]])
    return p @ A.T


def circle_points(n: int = 96) -> np.ndarray:
    t = np.linspace(0, 2 * math.pi, n, endpoint=False)
    return 0.5 * np.stack([np.cos(t), np.sin(t)], axis=1)


def square_points(n_per_side: int = 24) -> np.ndarray:
    corners = np.array([[-0.5, -0.5], [0.5, -0.5], [0.5, 0.5], [-0.5, 0.5]])
    pts = []
    for i in range(4):
        a, b = corners[i], corners[(i + 1) % 4]
        for k in range(n_per_side):
            pts.append(a + (b - a) * k / n_per_side)
    return np.array(pts)


# ----------------------------------------------------------------------------- drawing

def _px(points: np.ndarray, center, size: float) -> np.ndarray:
    return (points * size + np.asarray(center, dtype=np.float64)).astype(np.float32)


def draw_path(canvas: np.ndarray, pts_px: np.ndarray, thickness: float, color: int,
              rng: np.random.Generator | None = None, amount: float = 0.0, closed: bool = True) -> None:
    """Stroke a polyline. With amount>0 the width breathes along the path and a
    gap or two may appear, like a pen lifting."""
    pts = pts_px.reshape(-1, 1, 2)
    n = len(pts)
    if amount <= 0 or rng is None:
        cv2.polylines(canvas, [np.round(pts).astype(np.int32)], closed, color, max(1, int(round(thickness))), cv2.LINE_AA)
        return
    chunks = 24
    gap_count = rng.integers(1, 3) if rng.random() < 0.35 * amount else 0
    gap_starts = set(rng.integers(0, chunks, size=gap_count).tolist())
    idx = np.linspace(0, n, chunks + 1).astype(int)
    for c in range(chunks):
        if c in gap_starts:
            continue
        seg = pts[idx[c]:min(n, idx[c + 1] + 1)]
        if closed and c == chunks - 1:
            seg = np.concatenate([seg, pts[:1]])
        th = thickness * (1 + rng.normal(0, 0.18 * amount))
        cv2.polylines(canvas, [np.round(seg).astype(np.int32)], False, color, max(1, int(round(th))), cv2.LINE_AA)


def draw_glyph(canvas: np.ndarray, glyph: Glyph, center, size: float, thickness: float, color: int = 0,
               rng: np.random.Generator | None = None, amount: float = 0.0, paper: int = 255) -> None:
    """Draw one symbol (no frame). size is the glyph's bounding size in pixels."""
    rng = rng or np.random.default_rng(0)
    s = shapes()[glyph.symbol]
    R = rot_matrix(glyph.rotation * math.pi / 2)
    outer = perturb(s["outer"], rng, amount) @ R.T
    feats = [perturb(f, rng, amount) @ R.T for f in s["features"]]
    outer_px = _px(outer, center, size)
    feats_px = [_px(f, center, size) for f in feats]
    if glyph.fill:
        cv2.fillPoly(canvas, [np.round(outer_px).astype(np.int32)], color, cv2.LINE_AA)
        for f in feats_px:
            cv2.fillPoly(canvas, [np.round(f).astype(np.int32)], paper, cv2.LINE_AA)
            draw_path(canvas, f, thickness, color, rng, amount)
        if amount > 0:
            # hand fill: scribble streaks that leave a little paper showing through
            mask = np.zeros(canvas.shape[:2], np.uint8)
            cv2.fillPoly(mask, [np.round(outer_px).astype(np.int32)], 1)
            streaks = np.zeros_like(canvas)
            n_streaks = int(rng.integers(0, 10) * amount)
            ang = rng.uniform(0, math.pi)
            d = np.array([math.cos(ang), math.sin(ang)])
            for _ in range(n_streaks):
                off = (rng.uniform(-0.5, 0.5, size=2) * size) + np.asarray(center)
                a, b = off - d * size, off + d * size
                cv2.line(streaks, tuple(np.round(a).astype(int)), tuple(np.round(b).astype(int)), 255, 1, cv2.LINE_AA)
            lift = (streaks.astype(np.float32) * (mask > 0) * rng.uniform(0.3, 0.7))
            canvas[:] = np.clip(canvas.astype(np.float32) + lift, 0, 255).astype(np.uint8)
        draw_path(canvas, outer_px, thickness, color, rng, amount)
    else:
        draw_path(canvas, outer_px, thickness, color, rng, amount)
        for f in feats_px:
            draw_path(canvas, f, thickness, color, rng, amount)


def draw_frame(canvas: np.ndarray, frame: int, center, size: float, thickness: float, color: int = 0,
               rng: np.random.Generator | None = None, amount: float = 0.0) -> None:
    """Draw a square or circle frame of the given size (side or diameter) in pixels."""
    rng = rng or np.random.default_rng(0)
    if frame == FRAME_CIRCLE:
        pts = perturb(circle_points(), rng, amount)
        draw_path(canvas, _px(pts, center, size), thickness, color, rng, amount)
        return
    if amount <= 0:
        draw_path(canvas, _px(square_points(), center, size), thickness, color)
        return
    # hand-drawn square: four strokes with overshoot and a slightly rotated, wobbly outline
    base = perturb(square_points(), rng, amount * 0.6)
    corners = base[::24]
    for i in range(4):
        a, b = corners[i], corners[(i + 1) % 4]
        d = b - a
        ov1, ov2 = rng.uniform(-0.02, 0.08, size=2) * amount
        seg = np.stack([a - d * ov1, b + d * ov2])
        n = 24
        line = np.linspace(seg[0], seg[1], n)
        line += rng.normal(0, 0.004 * amount, size=line.shape).cumsum(axis=0) * 0.3
        draw_path(canvas, _px(line, center, size), thickness, color, rng, amount, closed=False)


@dataclass
class CellGeometry:
    byte: int
    center: tuple[float, float]
    size: float                      # frame side / diameter in px
    corners: np.ndarray              # 4x2 ideal square corners (tl, tr, br, bl), also for circles


def draw_cell(canvas: np.ndarray, byte: int, center, frame_size: float, thickness: float, color: int = 0,
              rng: np.random.Generator | None = None, amount: float = 0.0, paper: int = 255) -> CellGeometry:
    rng = rng or np.random.default_rng(0)
    g = unpack(byte)
    ratio = 0.62 if g.frame == 0 else 0.56
    ratio *= 1 + rng.normal(0, 0.06 * amount)
    c = np.asarray(center, dtype=np.float64) + rng.normal(0, 0.02 * frame_size * amount, size=2)
    draw_frame(canvas, g.frame, center, frame_size, thickness, color, rng, amount)
    draw_glyph(canvas, g, c, frame_size * ratio, thickness, color, rng, amount, paper)
    h = frame_size / 2
    corners = np.array([[center[0] - h, center[1] - h], [center[0] + h, center[1] - h],
                        [center[0] + h, center[1] + h], [center[0] - h, center[1] + h]])
    return CellGeometry(byte=byte, center=(float(center[0]), float(center[1])), size=frame_size, corners=corners)


@dataclass
class RowRender:
    canvas: np.ndarray
    cells: list[CellGeometry] = field(default_factory=list)
    baseline: tuple[tuple[float, float], tuple[float, float]] | None = None
    start_dot: tuple[float, float] | None = None


def render_row(data: bytes, cell: int = 120, thickness: float | None = None, hand: float = 0.0,
               rng: np.random.Generator | None = None, baseline: bool = True, margin: int | None = None,
               color: int = 0, paper: int = 255) -> RowRender:
    """Render a sequence of bytes as a row of framed symbols on an underline with a start dot."""
    rng = rng or np.random.default_rng(0)
    n = len(data)
    thickness = thickness or max(2.0, cell * 0.045)
    margin = margin if margin is not None else int(cell * 0.6)
    pitch = cell * 1.35
    W = int(margin * 2 + pitch * n)
    H = int(margin * 2 + cell * 1.5)
    canvas = np.full((H, W), paper, np.uint8)
    out = RowRender(canvas=canvas)
    y = margin + cell * 0.55
    for i, b in enumerate(data):
        x = margin + cell * 0.6 + pitch * i
        out.cells.append(draw_cell(canvas, b, (x, y), cell, thickness, color, rng, hand, paper))
    if baseline:
        y0 = y + cell * 0.72
        x0, x1 = margin * 0.5, W - margin * 0.5
        line = np.linspace([x0, y0], [x1, y0], 64)
        if hand > 0:
            line[:, 1] += rng.normal(0, 0.0025 * cell * hand, size=64).cumsum() * 0.5
        draw_path(canvas, line.astype(np.float32), thickness, color, rng, hand, closed=False)
        r = max(3, int(cell * 0.13))  # the start dot: about a quarter of a cell across
        cx, cy = int(x0), int(y0)
        cv2.circle(canvas, (cx, cy), r, color, -1, cv2.LINE_AA)
        out.baseline = ((x0, y0), (x1, y0))
        out.start_dot = (float(cx), float(cy))
    return out


def render_sheet(cell: int = 90, hand: float = 0.0, seed: int = 0) -> np.ndarray:
    """Reference sheet: one row per symbol; columns are 4 rotations outline then 4 filled,
    alternating square and circle frames."""
    rng = np.random.default_rng(seed)
    rows, cols = 16, 8
    pitch = int(cell * 1.25)
    canvas = np.full((pitch * rows + cell, pitch * cols + cell), 255, np.uint8)
    for s in range(16):
        for c in range(cols):
            fill, rot = divmod(c, 4)
            frame = (s + c) % 2
            b = pack(s, rot, fill, frame)
            draw_cell(canvas, b, (cell * 0.5 + pitch * c + cell * 0.1, cell * 0.5 + pitch * s + cell * 0.1),
                      cell, max(2, cell * 0.045), 0, rng, hand)
    return canvas
