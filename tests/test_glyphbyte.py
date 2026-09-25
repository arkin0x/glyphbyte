import os

import cv2
import numpy as np
import pytest

from glyphbyte import SYMBOLS, crc8, pack, unpack
from glyphbyte.detect import detect
from glyphbyte.pipeline import SymbolRead, _sequences
from glyphbyte.render import render_row, render_sheet
from glyphbyte.icons import as_json

MODEL = os.path.join(os.path.dirname(__file__), "..", "glyphbyte", "data", "model.onnx")


def test_pack_unpack_roundtrip():
    for b in range(256):
        g = unpack(b)
        assert pack(g.icon, g.dots) == b
        assert 0 <= g.icon < 16 and 0 <= g.dots < 16
    g = unpack(0x8A)
    assert g.name == "pie" and g.dot_corners() == ["top-left", "bottom-right"]
    assert g.describe() == "pie, dots top-left, bottom-right"
    assert unpack(0xE8).describe() == "star, dot top-left" and unpack(0x50).describe() == "arrow, no dots"


def test_crc8_known_vector():
    assert crc8(b"123456789") == 0xF4   # CRC-8/ATM check value


def test_icons_match_vocabulary():
    icons = as_json()
    assert [i["name"] for i in icons] == SYMBOLS and len(SYMBOLS) == 16
    for i in icons:
        assert 1 <= len(i["strokes"]) <= 2          # one or two pen strokes each
        for st in i["strokes"]:
            pts = np.array(st["points"])
            assert pts.shape[1] == 2 and len(pts) >= 2
            assert np.abs(pts).max() <= 0.5          # unit box


def test_dots_clear_icon_and_frame():
    from glyphbyte.icons import DOT_CORNERS, DOT_OFFSET, DOT_RADIUS, ICON_SCALE, strokes
    assert 0.5 - DOT_OFFSET - DOT_RADIUS >= 0.099
    for k in range(16):
        pts = np.vstack([p for p, _ in strokes(k)]) * ICON_SCALE
        for dx, dy in DOT_CORNERS:
            d = np.hypot(pts[:, 0] - dx * DOT_OFFSET, pts[:, 1] - dy * DOT_OFFSET).min() - DOT_RADIUS
            assert d >= 0.099, (SYMBOLS[k], dx, dy, d)


def test_render_row_geometry():
    row = render_row(bytes.fromhex("8a3a3a66"), cell=100)
    assert row.canvas.ndim == 2 and len(row.cells) == 4
    assert row.baseline is not None and row.start_dot is not None
    xs = [c.center[0] for c in row.cells]
    assert xs == sorted(xs)


def test_render_sheet_shape():
    sheet = render_sheet(cell=40)
    assert sheet.shape[0] > 16 * 40 and sheet.shape[1] > 16 * 40


@pytest.mark.parametrize("hand", [0.0, 0.5])
def test_detect_clean_row(hand):
    data = bytes.fromhex("8a3a3a6609eb")
    row = render_row(data, cell=110, hand=hand, rng=np.random.default_rng(3))
    det = detect(cv2.cvtColor(row.canvas, cv2.COLOR_GRAY2BGR))
    assert len(det.frames) == len(data)
    assert all(f.corners is not None for f in det.frames)
    assert det.baseline is not None and det.start_known
    assert det.direction[0] > 0.99 and det.up[1] < -0.99
    assert all(p.shape == (64, 64) for p in det.patches)


def test_sequences_fork_and_rank():
    reads = [
        SymbolRead(index=0, candidates=[(0x10, 0.7), (0x11, 0.3)], frame_conf=1.0),
        SymbolRead(index=1, candidates=[(0x20, 0.9), (0x24, 0.1)], frame_conf=1.0),
    ]
    seqs = _sequences(reads, max_sequences=8)
    assert seqs[0][0] == bytes([0x10, 0x20])
    assert len(seqs) == 4
    assert abs(sum(p for _, p in seqs) - 1.0) < 1e-9
    assert seqs[0][1] > seqs[1][1] >= seqs[2][1]


@pytest.mark.skipif(not os.path.exists(MODEL), reason="model not trained")
@pytest.mark.parametrize("hand", [0.0, 0.6])
def test_end_to_end_clean(hand):
    from glyphbyte.pipeline import read_image
    data = bytes.fromhex("8a3a3a6609eb01ff")
    row = render_row(data, cell=110, hand=hand, rng=np.random.default_rng(11))
    res = read_image(cv2.cvtColor(row.canvas, cv2.COLOR_GRAY2BGR))
    assert res.best == data, res.to_dict()


def test_spec_vectors_match_implementation():
    import json
    from glyphbyte.symbols import unpack
    spec = os.path.join(os.path.dirname(__file__), "..", "spec", "test-vectors.json")
    v = json.load(open(spec))
    assert v["format"] == 2 and v["symbols"] == SYMBOLS
    assert len(v["bytes"]) == 256
    for entry in v["bytes"]:
        g = unpack(entry["byte"])
        assert entry["text"] == g.describe()
        assert entry["icon"] == g.name and entry["icon_index"] == g.icon
        assert entry["dots"] == g.dot_corners() and entry["dots_value"] == g.dots
    for seq in v["sequences"]:
        assert seq["glyphs"] == [unpack(b).describe() for b in bytes.fromhex(seq["hex"])]


@pytest.mark.skipif(not os.path.exists(MODEL), reason="model not trained")
def test_spec_photo_vectors():
    import json
    from glyphbyte.pipeline import read_image
    spec_dir = os.path.join(os.path.dirname(__file__), "..", "spec")
    v = json.load(open(os.path.join(spec_dir, "test-vectors.json")))
    for ph in v["photos"]:
        img = cv2.imread(os.path.join(spec_dir, ph["image"]))
        res = read_image(img)
        assert any(b.hex() == ph["expected"] for b, _ in res.sequences), res.to_dict()


@pytest.mark.skipif(not os.path.exists(MODEL), reason="model not trained")
@pytest.mark.parametrize("turns", [1, 2, 3])
def test_glyphs_find_up_without_underline(turns):
    """v2 icons have a top: a row photographed turned, with no underline, still reads in order."""
    from glyphbyte.pipeline import read_image
    data = bytes.fromhex("e8ed3798c6ff")
    row = render_row(data, cell=110, hand=0.3, rng=np.random.default_rng(5), baseline=False)
    img = np.ascontiguousarray(np.rot90(row.canvas, turns))
    res = read_image(cv2.cvtColor(img, cv2.COLOR_GRAY2BGR))
    assert res.best == data, res.to_dict()


def test_handedness():
    from glyphbyte.detect import handed
    assert list(handed(np.array([0.0, -1.0]))) == [1.0, 0.0]      # upright: read to the right
    assert list(handed(np.array([1.0, 0.0]))) == [-0.0, 1.0]      # up points right: read downward
