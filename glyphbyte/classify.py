"""ONNX inference on rectified patches. No network, no torch at runtime."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources

import numpy as np

from .synth import PATCH


@dataclass
class PatchScores:
    sym_rot: np.ndarray   # 64 probabilities over symbol * 4 + rotation, renormalized without junk
    fill: np.ndarray      # 2 probabilities
    junk: float = 0.0     # probability that the patch is not a symbol at all (0 for 64-way models)


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
        sym = None
        fill = np.zeros((len(patches), 2), np.float64)
        for v in variants:
            ls, lf = self.session.run(None, {self.input_name: v})
            sym = _softmax(ls) if sym is None else sym + _softmax(ls)
            fill += _softmax(lf)
        sym /= len(variants)
        fill /= len(variants)
        out = []
        for i in range(len(patches)):
            junk = float(sym[i, 64]) if sym.shape[1] > 64 else 0.0
            real = sym[i, :64] / max(sym[i, :64].sum(), 1e-12)
            out.append(PatchScores(sym_rot=real, fill=fill[i], junk=junk))
        return out

    def junk_probabilities(self, patches: list[np.ndarray]) -> np.ndarray:
        return np.array([s.junk for s in self.predict(patches, tta=False)])
