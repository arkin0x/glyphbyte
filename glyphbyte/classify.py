"""ONNX inference on rectified patches. No network, no torch at runtime."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources

import numpy as np

from .synth import PATCH


@dataclass
class PatchScores:
    icon: np.ndarray      # 16 probabilities over the icons, renormalized without junk
    dots: np.ndarray      # 4 probabilities that each corner dot is present, top-left first
    junk: float = 0.0     # probability that the patch is not a glyph at all


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def _softmax(x: np.ndarray) -> np.ndarray:
    x = x - x.max(axis=-1, keepdims=True)
    e = np.exp(x)
    return e / e.sum(axis=-1, keepdims=True)


class Classifier:
    def __init__(self, model_path: str | None = None):
        import onnxruntime as ort
        if model_path is None:
            model_path = str(resources.files("glyphbyte.data").joinpath("model.onnx"))
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 2
        self.session = ort.InferenceSession(model_path, opts, providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name

    def predict(self, patches: list[np.ndarray], tta: bool = True) -> list[PatchScores]:
        if not patches:
            return []
        x = np.stack([p.astype(np.float32) / 255.0 for p in patches])[:, None]
        assert x.shape[-1] == PATCH and x.shape[-2] == PATCH
        variants = [x]
        if tta:
            variants.append(1.0 - x)  # the model is polarity invariant; averaging both views steadies it
        icon = None
        dots = np.zeros((len(patches), 4), np.float64)
        for v in variants:
            li, ld = self.session.run(None, {self.input_name: v})
            icon = _softmax(li) if icon is None else icon + _softmax(li)
            dots += _sigmoid(ld)
        icon /= len(variants)
        dots /= len(variants)
        out = []
        for i in range(len(patches)):
            junk = float(icon[i, 16])
            real = icon[i, :16] / max(icon[i, :16].sum(), 1e-12)
            out.append(PatchScores(icon=real, dots=dots[i], junk=junk))
        return out

    def junk_probabilities(self, patches: list[np.ndarray]) -> np.ndarray:
        return np.array([s.junk for s in self.predict(patches, tta=False)])
