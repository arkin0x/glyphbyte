"""ONNX inference on rectified patches. No network, no torch at runtime.

A model file says which format it reads by its outputs: format 2 models have the heads
icon, dots, junk and orient; format 1 models have sym_rot (64 pictogram x rotation
classes plus junk) and fill.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources

import numpy as np

from .synth import PATCH


@dataclass
class PatchScores:
    fmt: int
    junk: float = 0.0                   # probability that the patch is not a glyph at all
    # format 2
    icon: np.ndarray | None = None      # 16 probabilities over the icons, for an upright patch
    dots: np.ndarray | None = None      # 4 probabilities that each corner dot is present, top-left first
    orient: np.ndarray | None = None    # 4 probabilities: the glyph is turned k quarter turns counter-clockwise
    # format 1
    sym_rot: np.ndarray | None = None   # 64 probabilities over pictogram * 4 + rotation
    fill: np.ndarray | None = None      # 2 probabilities: outline, filled


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def _softmax(x: np.ndarray) -> np.ndarray:
    x = x - x.max(axis=-1, keepdims=True)
    e = np.exp(x)
    return e / e.sum(axis=-1, keepdims=True)


def default_model(fmt: int = 2, small: bool = False) -> str:
    name = ("model-small" if small else "model") + ("-v1" if fmt == 1 else "") + ".onnx"
    return str(resources.files("glyphbyte.data").joinpath(name))


class Classifier:
    def __init__(self, model_path: str | None = None):
        import onnxruntime as ort
        model_path = model_path or default_model(2)
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 2
        self.session = ort.InferenceSession(model_path, opts, providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name
        outputs = [o.name for o in self.session.get_outputs()]
        self.fmt = 2 if "icon" in outputs else 1

    def predict(self, patches: list[np.ndarray], tta: bool = True) -> list[PatchScores]:
        if not patches:
            return []
        x = np.stack([p.astype(np.float32) / 255.0 for p in patches])[:, None]
        assert x.shape[-1] == PATCH and x.shape[-2] == PATCH
        variants = [x, 1.0 - x] if tta else [x]   # polarity invariant: averaging both views steadies it
        n, k = len(patches), len(variants)
        if self.fmt == 1:
            sym = np.zeros((n, 65))
            fill = np.zeros((n, 2))
            for v in variants:
                ls, lf = self.session.run(None, {self.input_name: v})
                sym += _softmax(ls)
                fill += _softmax(lf)
            sym, fill = sym / k, fill / k
            real = sym[:, :64] / np.maximum(sym[:, :64].sum(1, keepdims=True), 1e-12)
            return [PatchScores(fmt=1, junk=float(sym[i, 64]), sym_rot=real[i], fill=fill[i]) for i in range(n)]
        icon = np.zeros((n, 16))
        dots = np.zeros((n, 4))
        junk = np.zeros(n)
        orient = np.zeros((n, 4))
        for v in variants:
            li, ld, lj, lo = self.session.run(None, {self.input_name: v})
            icon += _softmax(li)
            dots += _sigmoid(ld)
            junk += _sigmoid(lj[:, 0])
            orient += _softmax(lo)
        return [PatchScores(fmt=2, junk=float(junk[i] / k), icon=icon[i] / k, dots=dots[i] / k, orient=orient[i] / k)
                for i in range(n)]

    def junk_probabilities(self, patches: list[np.ndarray]) -> np.ndarray:
        return np.array([s.junk for s in self.predict(patches, tta=False)])


def load_classifiers(model: str | None = None, model_v1: str | None = None, small: bool = False,
                     formats=(2, 1)) -> dict[int, Classifier]:
    """Classifiers by format: the bundled ones unless paths are given."""
    out = {}
    if 2 in formats:
        out[2] = Classifier(model or default_model(2, small))
    if 1 in formats:
        out[1] = Classifier(model_v1 or default_model(1, small))
    return out
