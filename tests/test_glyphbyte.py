import os

import cv2
import numpy as np
import pytest

from glyphbyte import SYMBOLS, crc8, pack, unpack
from glyphbyte.detect import detect
from glyphbyte.pipeline import SymbolRead, _sequences
from glyphbyte.render import render_row, render_sheet
from glyphbyte.symbols import load_canonical

MODEL = os.path.join(os.path.dirname(__file__), "..", "glyphbyte", "data", "model.onnx")


def test_pack_unpack_roundtrip():
    for b in range(256):
        g = unpack(b)
        assert pack(g.symbol, g.rotation, g.fill, g.frame) == b
        assert 0 <= g.symbol < 16 and 0 <= g.rotation < 4
    assert unpack(0x8A).name == "arrow" and unpack(0x8A).rotation == 2 and unpack(0x8A).fill == 1 and unpack(0x8A).frame == 0


def test_crc8_known_vector():
    assert crc8(b"123456789") == 0xF4   # CRC-8/ATM check value


def test_canonical_matches_vocabulary():
    shapes = load_canonical()
    assert [s["name"] for s in shapes] == SYMBOLS
    for s in shapes:
        pts = np.array(s["outer"])
        assert pts.shape[1] == 2 and len(pts) >= 32
        assert np.abs(pts).max() <= 0.51   # unit box


def test_render_row_geometry():
    row = render_row(bytes.fromhex("8a3a3a66"), cell=100)
    assert row.canvas.ndim == 2 and len(row.cells) == 4
    assert row.baseline is not None and row.start_dot is not None
    xs = [c.center[0] for c in row.cells]
    assert xs == sorted(xs)


def test_render_sheet_shape():
    sheet = render_sheet(cell=40)
    assert sheet.shape[0] > 16 * 40 and sheet.shape[1] > 8 * 40


@pytest.mark.parametrize("hand", [0.0, 0.5])
def test_detect_clean_row(hand):
    data = bytes.fromhex("8a3a3a6609eb")
    row = render_row(data, cell=110, hand=hand, rng=np.random.default_rng(3))
    det = detect(cv2.cvtColor(row.canvas, cv2.COLOR_GRAY2BGR))
    assert len(det.frames) == len(data)
    assert [f.kind for f in det.frames] == [b & 1 for b in data]
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
    assert v["symbols"] == SYMBOLS
    assert len(v["bytes"]) == 256
    for entry in v["bytes"]:
        g = unpack(entry["byte"])
        assert entry["text"] == g.describe()
        assert entry["symbol"] == g.name and entry["rotation_deg"] == g.rotation * 90
        assert entry["fill"] == ("filled" if g.fill else "outline") and entry["frame"] == ("circle" if g.frame else "square")
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
