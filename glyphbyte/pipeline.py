"""Image in, candidate byte sequences out.

Uncertainty is not hidden: every symbol keeps its ranked candidate bytes, and the
result lists the most probable whole sequences so a caller can query all of them
(cheap on nostr) and let a person pick the one that matches what they see.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field

import numpy as np

from .classify import Classifier, PatchScores
from .detect import Detection, detect
from .symbols import Glyph, unpack


@dataclass
class SymbolRead:
    index: int
    candidates: list[tuple[int, float]]      # (byte, probability) best first
    frame_conf: float

    @property
    def byte(self) -> int:
        return self.candidates[0][0]

    @property
    def glyph(self) -> Glyph:
        return unpack(self.byte)

    @property
    def confidence(self) -> float:
        return self.candidates[0][1]


@dataclass
class Result:
    reads: list[SymbolRead]
    sequences: list[tuple[bytes, float]]     # (bytes, joint probability) best first
    warnings: list[str] = field(default_factory=list)
    detection: Detection | None = None

    @property
    def best(self) -> bytes:
        return self.sequences[0][0] if self.sequences else b""

    def to_dict(self) -> dict:
        return {
            "best": self.best.hex(),
            "sequences": [{"hex": b.hex(), "p": round(p, 4)} for b, p in self.sequences],
            "symbols": [
                {"index": r.index, "byte": r.byte, "glyph": r.glyph.describe(), "p": round(r.confidence, 4),
                 "candidates": [{"byte": b, "glyph": unpack(b).describe(), "p": round(p, 4)} for b, p in r.candidates]}
                for r in self.reads
            ],
            "warnings": self.warnings,
        }


def _byte_distribution(scores: PatchScores, frame_kind: int, frame_conf: float) -> np.ndarray:
    """Joint probability over all 256 bytes for one cell."""
    p_frame = np.array([0.5, 0.5])
    p_frame[frame_kind] = 0.5 + 0.5 * frame_conf
    p_frame[1 - frame_kind] = 0.5 - 0.5 * frame_conf
    dist = np.zeros(256)
    for sr in range(64):
        for fill in (0, 1):
            for frame in (0, 1):
                b = (sr << 2) | (fill << 1) | frame
                dist[b] = scores.sym_rot[sr] * scores.fill[fill] * p_frame[frame]
    return dist / max(dist.sum(), 1e-12)


def _candidates(dist: np.ndarray, fork_ratio: float, max_per_symbol: int) -> list[tuple[int, float]]:
    order = np.argsort(-dist)
    top = dist[order[0]]
    out = [(int(order[0]), float(top))]
    for b in order[1:max_per_symbol]:
        if dist[b] >= fork_ratio * top:
            out.append((int(b), float(dist[b])))
    return out


def _sequences(reads: list[SymbolRead], max_sequences: int) -> list[tuple[bytes, float]]:
    beam: list[tuple[list[int], float]] = [([], 1.0)]
    for r in reads:
        nxt = []
        for seq, p in beam:
            for b, pb in r.candidates:
                nxt.append((seq + [b], p * pb))
        nxt.sort(key=lambda t: -t[1])
        beam = nxt[:max_sequences]
    total = sum(p for _, p in beam) or 1.0
    return [(bytes(seq), p / total) for seq, p in beam]


def read_image(image: np.ndarray, classifier: Classifier | None = None, max_sequences: int = 8,
               fork_ratio: float = 0.2, max_per_symbol: int = 4) -> Result:
    classifier = classifier or Classifier()
    det = detect(image, junk_fn=classifier.junk_probabilities)
    warnings = list(det.warnings)
    if not det.frames:
        return Result(reads=[], sequences=[], warnings=warnings + ["no symbols found"], detection=det)
    scores = classifier.predict(det.patches)
    reads = []
    for i, (f, sc) in enumerate(zip(det.frames, scores)):
        dist = _byte_distribution(sc, f.kind, f.quad_ratio)
        reads.append(SymbolRead(index=i, candidates=_candidates(dist, fork_ratio, max_per_symbol), frame_conf=f.quad_ratio))
    sequences = _sequences(reads, max_sequences)
    if det.baseline is not None and not det.start_known:
        # reading direction unknown: offer the reversed sequence too
        rev = [(bytes(reversed(b)), p * 0.5) for b, p in sequences]
        sequences = sorted([(b, p * 0.5) for b, p in sequences] + rev, key=lambda t: -t[1])[:max_sequences]
        warnings.append("reading direction unknown: sequences include the reversed order")
    return Result(reads=reads, sequences=sequences, warnings=warnings, detection=det)
