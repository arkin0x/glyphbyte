"""Render glyphbyte v2 glyphs, frames and rows, either clean or in a hand-drawn style.

Coordinates are image coordinates (y down). Rotation r in quarter turns is
clockwise on screen. Canvases are uint8 grayscale, white paper, dark ink.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import cv2
import numpy as np

from .icons import DOT_CORNERS, DOT_OFFSET, DOT_RADIUS, ICON_SCALE, strokes
from .symbols import FRAME_CIRCLE, FRAME_SQUARE, Glyph, unpack


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


def _resample(points: np.ndarray, closed: bool, step: float = 0.02) -> np.ndarray:
    """Evenly spaced points along a polyline, so the wobble model has a smooth path to bend."""
    p = np.vstack([points, points[:1]]) if closed else points
    seg = np.linalg.norm(np.diff(p, axis=0), axis=1)
    s = np.concatenate([[0], np.cumsum(seg)])
    n = max(8, int(s[-1] / step))
    t = np.linspace(0, s[-1], n, endpoint=not closed)
    # keep the corners: a hand slows down at a corner and keeps it
    t = np.unique(np.concatenate([t, s[:-1] if closed else s]))
    return np.stack([np.interp(t, s, p[:, 0]), np.interp(t, s, p[:, 1])], axis=1)


def _open_wobble(points: np.ndarray, rng: np.random.Generator, amount: float) -> np.ndarray:
    """perturb() for an open stroke: the same wobble without assuming the path closes."""
    n = len(points)
    t = np.linspace(0, 1, n)
    disp = np.zeros((n, 2))
    for _ in range(2):
        f = rng.uniform(0.5, 2.5)
        disp += rng.uniform(0, 0.025) * amount * np.sin(2 * math.pi * f * t[:, None] + rng.uniform(0, 2 * math.pi, 2))
    return points + disp + rng.normal(0, 0.004 * amount, (n, 2))


def draw_dot(canvas: np.ndarray, center, r: float, thickness: float, color: int,
             rng: np.random.Generator | None = None, amount: float = 0.0) -> None:
    """A dot as people draw one: usually a filled blob, sometimes a scribble or a tiny ring."""
    c = np.asarray(center, np.float64)
    if amount <= 0 or rng is None:
        cv2.circle(canvas, tuple(np.round(c * 4).astype(int)), max(1, int(round(r * 4))), color, -1, cv2.LINE_AA, shift=2)
        return
    r = r * rng.uniform(0.7, 1.4)
    style = rng.random()
    if style < 0.1:      # a tiny ring; with a thick tool it fills in
        cv2.circle(canvas, tuple(np.round(c * 4).astype(int)), max(1, int(round(r * 0.8 * 4))), color,
                   max(1, int(round(max(thickness, r * 0.6)))), cv2.LINE_AA, shift=2)
    elif style < 0.35:   # a scribbled blob
        k = 12
        t = np.linspace(0, 2 * math.pi, k, endpoint=False)
        rr = r * (1 + rng.normal(0, 0.18, k))
        pts = np.stack([c[0] + rr * np.cos(t), c[1] + rr * np.sin(t)], 1)
        cv2.fillPoly(canvas, [np.round(pts * 4).astype(np.int32)], color, cv2.LINE_AA, shift=2)
    else:
        cv2.circle(canvas, tuple(np.round(c * 4).astype(int)), max(1, int(round(r * 4))), color, -1, cv2.LINE_AA, shift=2)


def draw_glyph(canvas: np.ndarray, glyph: Glyph, center, frame_size: float, thickness: float, color: int = 0,
               rng: np.random.Generator | None = None, amount: float = 0.0) -> None:
    """Draw one glyph's icon and corner dots (no frame). frame_size is the frame side in pixels."""
    rng = rng or np.random.default_rng(0)
    c = np.asarray(center, dtype=np.float64)
    size = frame_size * ICON_SCALE
    if amount > 0:
        # the writer's icon: a little bigger or smaller, a little off centre, tilted, sheared
        size *= 1 + rng.normal(0, 0.1 * amount)
        c = c + rng.normal(0, 0.03 * frame_size * amount, 2)
        theta = rng.normal(0, math.radians(5) * amount)
        A = rot_matrix(theta) @ (np.eye(2) + rng.normal(0, 0.05 * amount, (2, 2)))
    else:
        A = np.eye(2)
    for pts, closed in strokes(glyph.icon):
        q = _resample(pts, closed)
        if amount > 0:
            q = perturb(q, rng, amount * 0.8) if closed else _open_wobble(q, rng, amount)
        draw_path(canvas, _px(q @ A.T, c, size), thickness, color, rng, amount, closed=closed)
    fc = np.asarray(center, dtype=np.float64)
    for i, (dx, dy) in enumerate(DOT_CORNERS):
        if glyph.dots >> (3 - i) & 1:
            p = fc + np.array([dx, dy]) * DOT_OFFSET * frame_size
            if amount > 0:
                p = p + rng.normal(0, 0.02 * frame_size * amount, 2)
            draw_dot(canvas, p, DOT_RADIUS * frame_size, thickness, color, rng, amount)


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
    draw_frame(canvas, FRAME_SQUARE, center, frame_size, thickness, color, rng, amount)
    draw_glyph(canvas, unpack(byte), center, frame_size, thickness, color, rng, amount)
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
    """Reference sheet: all 256 glyphs, row = icon (first hex digit), column = dots (second)."""
    rng = np.random.default_rng(seed)
    pitch = int(cell * 1.2)
    canvas = np.full((pitch * 16 + cell // 2, pitch * 16 + cell // 2), 255, np.uint8)
    for b in range(256):
        r, c = divmod(b, 16)
        draw_cell(canvas, b, (cell * 0.75 + pitch * c, cell * 0.75 + pitch * r), cell, max(2, cell * 0.04), 0, rng, hand)
    return canvas
