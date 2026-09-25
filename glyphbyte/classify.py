"""ONNX inference on rectified patches. No network, no torch at runtime."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources

import numpy as np

from .synth import PATCH


@dataclass
class PatchScores:
    icon: np.ndarray      # 16 probabilities over the icons, for an upright patch
    dots: np.ndarray      # 4 probabilities that each corner dot is present, top-left first
    junk: float = 0.0     # probability that the patch is not a glyph at all, in any rotation
    orient: np.ndarray | None = None   # 4 probabilities: the glyph is turned k quarter turns counter-clockwise


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
        icon = np.zeros((len(patches), 16))
        dots = np.zeros((len(patches), 4))
        junk = np.zeros(len(patches))
        orient = np.zeros((len(patches), 4))
        for v in variants:
            li, ld, lj, lo = self.session.run(None, {self.input_name: v})
            icon += _softmax(li)
            dots += _sigmoid(ld)
            junk += _sigmoid(lj[:, 0])
            orient += _softmax(lo)
        k = len(variants)
        return [PatchScores(icon=icon[i] / k, dots=dots[i] / k, junk=float(junk[i] / k), orient=orient[i] / k)
                for i in range(len(patches))]

    def junk_probabilities(self, patches: list[np.ndarray]) -> np.ndarray:
        return np.array([s.junk for s in self.predict(patches, tta=False)])
