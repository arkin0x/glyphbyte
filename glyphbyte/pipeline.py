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
from .detect import Detection, detect, handed, rectify_frame
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


def _byte_distribution(scores: PatchScores) -> np.ndarray:
    """Joint probability over all 256 bytes for one cell: icon times each dot bit."""
    p_dots = np.ones(16)
    for n in range(16):
        for k in range(4):
            on = n >> (3 - k) & 1
            p_dots[n] *= scores.dots[k] if on else 1.0 - scores.dots[k]
    dist = np.outer(scores.icon, p_dots).ravel()     # index = icon << 4 | dots
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


# how much more likely (in nats, summed over the row) a turned reading must be before the
# glyphs overrule the underline; below this both readings are kept as candidates
ORIENT_MARGIN = 2.0


def _turn(up: np.ndarray, d: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray]:
    """True (up, d) when the glyphs in patches cut with (up, d) look turned k quarter turns
    counter-clockwise: k=1 means their tops point along -d."""
    for _ in range(k % 4):
        up, d = -d, up
    return up, d


def _orientation(det: Detection, scores: list[PatchScores]) -> list[tuple[int, float]]:
    """Log-likelihood of each quarter turn of the whole row, best first. With an underline
    only 0 and 2 are possible (the line fixes the axis); without one, all four."""
    turns = (0, 2) if det.baseline is not None else (0, 1, 2, 3)
    ll = {k: float(sum(np.log(max(float(sc.orient[k]), 1e-6)) for sc in scores)) for k in turns}
    return sorted(ll.items(), key=lambda t: -t[1])


def _reorient(det: Detection, k: int, classifier: Classifier):
    """Frames in reading order, their patches and scores, and (up, d), for the row turned by k."""
    up, d = _turn(det.up, det.direction, k)
    frames = sorted(det.frames, key=lambda f: float(f.center @ d))
    patches = [rectify_frame(det.gray, f, d, up, det.light_ink) for f in frames]
    return frames, patches, classifier.predict(patches), up, d


def _reads(frames, scores, fork_ratio, max_per_symbol) -> list[SymbolRead]:
    return [SymbolRead(index=i, candidates=_candidates(_byte_distribution(sc), fork_ratio, max_per_symbol),
                       frame_conf=f.quad_ratio) for i, (f, sc) in enumerate(zip(frames, scores))]


def read_image(image: np.ndarray, classifier: Classifier | None = None, max_sequences: int = 8,
               fork_ratio: float = 0.2, max_per_symbol: int = 4) -> Result:
    classifier = classifier or Classifier()
    det = detect(image, junk_fn=classifier.junk_probabilities)
    warnings = list(det.warnings)
    if not det.frames:
        return Result(reads=[], sequences=[], warnings=warnings + ["no glyphs found"], detection=det)
    scores = classifier.predict(det.patches)
    frames = det.frames
    # every icon but box, plus and x has a top: the glyphs vote on which way the row is turned
    ranked = _orientation(det, scores)
    (k_best, ll_best), (k_next, ll_next) = ranked[0], ranked[1]
    ll_zero = dict(ranked)[0]
    turned = None
    if k_best != 0 and ll_best - ll_zero > ORIENT_MARGIN:
        frames, patches, scores, up, d = _reorient(det, k_best, classifier)
        det.up, det.direction, det.frames, det.patches = up, d, frames, patches
        warnings.append(f"the glyphs read turned {90 * k_best} degrees from the underline's side; turned the row")
        k_best = 0
    elif k_best != 0 or ll_best - ll_next < ORIENT_MARGIN:
        # not sure: keep the runner-up orientation as a second family of candidates
        turned = k_next if k_best == 0 else k_best
    reads = _reads(frames, scores, fork_ratio, max_per_symbol)
    sequences = _sequences(reads, max_sequences)
    if turned is not None and not det.start_known:
        f2, _, s2, _, _ = _reorient(det, turned, classifier)
        seq2 = _sequences(_reads(f2, s2, fork_ratio, max_per_symbol), max_sequences)
        # weigh the two families by the vote
        w = 1.0 / (1.0 + np.exp(ll_zero - dict(ranked)[turned]))
        sequences = sorted([(b, p * (1 - w)) for b, p in sequences] + [(b, p * w) for b, p in seq2],
                           key=lambda t: -t[1])[:max_sequences]
        warnings.append(f"not sure which way is up: candidates include the row turned {90 * turned} degrees")
    return Result(reads=reads, sequences=sequences, warnings=warnings, detection=det)
