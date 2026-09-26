"""Image in, candidate byte sequences out, in whichever format the row was drawn.

Uncertainty is not hidden: every glyph keeps its ranked candidate bytes, and the
result lists the most probable whole sequences so a caller can query all of them
(cheap on nostr) and let a person pick the one that matches what they see.

Formats: the row is found once, then read as format 2 (icons and corner dots, the
default) and as format 1 (the first alphabet of rotated, filled pictograms). The
format whose model explains the glyphs better wins; when the two are close, the
other format's readings stay in the list as candidates, each tagged with its format.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import NamedTuple

import numpy as np

from . import v1
from .classify import Classifier, PatchScores, load_classifiers
from .detect import Detection, detect, rectify_frame
from .symbols import DEFAULT_FORMAT, describe

# how much more likely (nats, summed over the row) a turned reading must be before the
# glyphs overrule the underline; below this both readings are kept as candidates
ORIENT_MARGIN = 2.0
# format choice, fitted on 583 synthetic rows of both formats (2026-09-26): read format 1 when
# its log-likelihood per glyph beats format 2's by more than FORMAT_BIAS (95% of v1 rows and
# 96-97% of v2 rows go to the right format); keep the other format's readings as candidates
# while the difference is within FORMAT_FORK of that threshold
FORMAT_BIAS = 0.5
FORMAT_FORK = 0.5
RESCUE = 0.3          # the other format's model must be this sure a rejected candidate is a glyph


class Reading(NamedTuple):
    bytes: bytes
    p: float
    fmt: int


@dataclass
class SymbolRead:
    index: int
    candidates: list[tuple[int, float]]      # (byte, probability) best first
    frame_conf: float
    fmt: int = DEFAULT_FORMAT

    @property
    def byte(self) -> int:
        return self.candidates[0][0]

    @property
    def confidence(self) -> float:
        return self.candidates[0][1]

    def describe(self, byte: int | None = None) -> str:
        return describe(self.byte if byte is None else byte, self.fmt)


@dataclass
class Result:
    reads: list[SymbolRead]
    sequences: list[Reading]                 # best first; each tagged with its format
    warnings: list[str] = field(default_factory=list)
    detection: Detection | None = None
    fmt: int = DEFAULT_FORMAT                # the format the row was read as
    format_scores: dict = field(default_factory=dict)   # row log-likelihood per format that was tried

    @property
    def best(self) -> bytes:
        return self.sequences[0].bytes if self.sequences else b""

    def to_dict(self) -> dict:
        return {
            "best": self.best.hex(),
            "format": self.fmt,
            "sequences": [{"hex": s.bytes.hex(), "p": round(s.p, 4), "format": s.fmt} for s in self.sequences],
            "symbols": [
                {"index": r.index, "byte": r.byte, "glyph": r.describe(), "p": round(r.confidence, 4),
                 "candidates": [{"byte": b, "glyph": r.describe(b), "p": round(p, 4)} for b, p in r.candidates]}
                for r in self.reads
            ],
            "warnings": self.warnings,
        }


# ----------------------------------------------------------------------------- per glyph

def _dist_v2(sc: PatchScores) -> np.ndarray:
    """Joint probability over all 256 bytes for one format 2 cell: icon times each dot bit."""
    p_dots = np.ones(16)
    for n in range(16):
        for k in range(4):
            p_dots[n] *= sc.dots[k] if n >> (3 - k) & 1 else 1.0 - sc.dots[k]
    dist = np.outer(sc.icon, p_dots).ravel()     # index = icon << 4 | dots
    return dist / max(dist.sum(), 1e-12)


def _dist_v1(sc: PatchScores, frame_kind: int, frame_conf: float) -> np.ndarray:
    """Joint probability over all 256 bytes for one format 1 cell: pictogram and rotation,
    fill, and the frame's shape as the detector saw it."""
    p_frame = np.array([0.5, 0.5])
    p_frame[frame_kind] = 0.5 + 0.5 * frame_conf
    p_frame[1 - frame_kind] = 0.5 - 0.5 * frame_conf
    dist = (sc.sym_rot[:, None, None] * sc.fill[None, :, None] * p_frame[None, None, :]).ravel()
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


def _row_ll(dists: list[np.ndarray]) -> float:
    """How well a format explains the row: the summed log probability of each glyph's best byte."""
    return float(sum(np.log(max(float(d.max()), 1e-12)) for d in dists))


# ----------------------------------------------------------------------------- per format

@dataclass
class _FormatRead:
    fmt: int
    reads: list[SymbolRead]
    sequences: list[Reading]
    ll: float
    warnings: list[str]
    frames: list = field(default_factory=list)
    patches: list = field(default_factory=list)
    up: np.ndarray | None = None
    d: np.ndarray | None = None


def _turn(up: np.ndarray, d: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray]:
    """True (up, d) when the glyphs in patches cut with (up, d) look turned k quarter turns
    counter-clockwise: k=1 means their tops point along -d."""
    for _ in range(k % 4):
        up, d = -d, up
    return up, d


def _cut(det: Detection, up, d, fmt: int):
    frames = sorted(det.frames, key=lambda f: float(f.center @ d))
    return frames, [rectify_frame(det.gray, f, d, up, det.light_ink, fmt) for f in frames]


def _read_v2(det: Detection, clf: Classifier, fork_ratio: float, max_per: int, max_seq: int) -> _FormatRead:
    warnings: list[str] = []
    frames, patches = det.frames, det.patches
    up, d = det.up, det.direction
    scores = clf.predict(patches)
    # every icon but box, plus and x has a top: the glyphs vote on which way the row is turned
    turns = (0, 2) if det.baseline is not None else (0, 1, 2, 3)
    ll = {k: float(sum(np.log(max(float(sc.orient[k]), 1e-6)) for sc in scores)) for k in turns}
    ranked = sorted(ll, key=lambda k: -ll[k])
    k_best = ranked[0]
    turned = None
    if k_best != 0 and ll[k_best] - ll[0] > ORIENT_MARGIN:
        up, d = _turn(det.up, det.direction, k_best)
        frames, patches = _cut(det, up, d, 2)
        scores = clf.predict(patches)
        warnings.append(f"the glyphs read turned {90 * k_best} degrees from the underline's side; turned the row")
    elif k_best != 0 or ll[ranked[0]] - ll[ranked[1]] < ORIENT_MARGIN:
        turned = ranked[1] if k_best == 0 else k_best
    dists = [_dist_v2(sc) for sc in scores]
    reads = [SymbolRead(index=i, candidates=_candidates(dd, fork_ratio, max_per), frame_conf=f.quad_ratio, fmt=2)
             for i, (f, dd) in enumerate(zip(frames, dists))]
    seqs = [Reading(b, p, 2) for b, p in _sequences(reads, max_seq)]
    if turned is not None and not det.start_known:
        up2, d2 = _turn(det.up, det.direction, turned)
        f2, p2 = _cut(det, up2, d2, 2)
        reads2 = [SymbolRead(index=i, candidates=_candidates(_dist_v2(sc), fork_ratio, max_per), frame_conf=f.quad_ratio, fmt=2)
                  for i, (f, sc) in enumerate(zip(f2, clf.predict(p2)))]
        w = 1.0 / (1.0 + np.exp(ll[0] - ll[turned]))
        seqs = sorted([Reading(b, p * (1 - w), 2) for b, p, _ in seqs] +
                      [Reading(b, p * w, 2) for b, p in _sequences(reads2, max_seq)], key=lambda s: -s.p)[:max_seq]
        warnings.append(f"not sure which way is up: candidates include the row turned {90 * turned} degrees")
    return _FormatRead(2, reads, seqs, _row_ll(dists), warnings, frames, patches, up, d)


def _read_v1(det: Detection, clf: Classifier, fork_ratio: float, max_per: int, max_seq: int) -> _FormatRead:
    warnings: list[str] = []
    frames, patches = _cut(det, det.up, det.direction, 1)
    dists = [_dist_v1(sc, f.kind, f.quad_ratio) for sc, f in zip(clf.predict(patches), frames)]
    reads = [SymbolRead(index=i, candidates=_candidates(dd, fork_ratio, max_per), frame_conf=f.quad_ratio, fmt=1)
             for i, (f, dd) in enumerate(zip(frames, dists))]
    seqs = [Reading(b, p, 1) for b, p in _sequences(reads, max_seq)]
    if not det.start_known:
        # v1 pictograms are drawn in every rotation, so they cannot say which way is up: the row
        # turned 180 degrees reads in reverse, every glyph's rotation two quarter turns on
        rev = [Reading(bytes(v1.turned(b, 2) for b in reversed(s.bytes)), s.p * 0.5, 1) for s in seqs]
        seqs = sorted([Reading(s.bytes, s.p * 0.5, 1) for s in seqs] + rev, key=lambda s: -s.p)[:max_seq]
        warnings.append("format 1 has no top to read: candidates include the row turned 180 degrees")
    return _FormatRead(1, reads, seqs, _row_ll(dists), warnings, frames, patches, det.up, det.direction)


# ----------------------------------------------------------------------------- entry

_DEFAULT: dict[int, Classifier] | None = None


def _classifiers(classifier) -> dict[int, Classifier]:
    global _DEFAULT
    if isinstance(classifier, dict):
        return classifier
    if isinstance(classifier, Classifier):
        return {classifier.fmt: classifier}
    if _DEFAULT is None:
        _DEFAULT = load_classifiers()
    return _DEFAULT


def _junk_fn(clfs: dict[int, Classifier]):
    """Probability that a candidate frame holds no glyph of any format, in any rotation. Format 2
    decides; format 1 gets a second look only at what format 2 rejects."""
    up, d = np.array([0.0, -1.0]), np.array([1.0, 0.0])

    def fn(gray, frames):
        fmts = sorted(clfs, reverse=True)
        pj = clfs[fmts[0]].junk_probabilities([rectify_frame(gray, f, d, up, f.light_ink, fmts[0]) for f in frames])
        for fmt in fmts[1:]:
            idx = [i for i, p in enumerate(pj) if p > 0.5]
            if idx:
                p2 = clfs[fmt].junk_probabilities([rectify_frame(gray, frames[i], d, up, frames[i].light_ink, fmt) for i in idx])
                for i, p in zip(idx, p2):
                    if p < RESCUE:          # only a clear glyph of the other format overrules
                        pj[i] = min(pj[i], p)
        return pj
    return fn


def read_image(image: np.ndarray, classifier: Classifier | dict[int, Classifier] | None = None,
               max_sequences: int = 8, fork_ratio: float = 0.2, max_per_symbol: int = 4,
               fmt: int | str = "auto") -> Result:
    """Read a photo. `classifier` is one Classifier (its format only), a dict {format:
    Classifier}, or None for the bundled models. `fmt` is "auto" (both formats, the better
    one wins), 1 or 2."""
    clfs = _classifiers(classifier)
    if fmt != "auto":
        if int(fmt) not in clfs:
            clfs = {**clfs, **load_classifiers(formats=(int(fmt),))}
        clfs = {int(fmt): clfs[int(fmt)]}
    det = detect(image, junk_fn=_junk_fn(clfs))
    warnings = list(det.warnings)
    if not det.frames:
        return Result(reads=[], sequences=[], warnings=warnings + ["no glyphs found"], detection=det,
                      fmt=max(clfs))
    readers = {2: _read_v2, 1: _read_v1}
    results = {}
    for f in sorted(clfs, reverse=True):
        # format 1 wins only by beating format 2 by FORMAT_BIAS per glyph, and a log-likelihood is at
        # most 0: when format 2 is above -FORMAT_BIAS per glyph, format 1 cannot win and is not read
        if f == 1 and 2 in results and results[2].ll / max(1, len(det.frames)) > -FORMAT_BIAS:
            continue
        results[f] = readers[f](det, clfs[f], fork_ratio, max_per_symbol, max_sequences)
    if len(results) == 1:
        (chosen,) = results.values()
        sequences = chosen.sequences
    else:
        n = max(1, len(det.frames))
        margin = (results[1].ll - results[2].ll) / n - FORMAT_BIAS  # per glyph; > 0 favours format 1
        chosen = results[1] if margin > 0 else results[2]
        other = results[2] if margin > 0 else results[1]
        sequences = chosen.sequences
        if abs(margin) < FORMAT_FORK:
            w = 1.0 / (1.0 + np.exp(abs(margin) * n))                # the other format's share
            sequences = sorted([Reading(s.bytes, s.p * (1 - w), s.fmt) for s in chosen.sequences] +
                               [Reading(s.bytes, s.p * w, s.fmt) for s in other.sequences],
                               key=lambda s: -s.p)[:max_sequences]
            warnings.append(f"the row could be format {other.fmt}: its readings are among the candidates")
        if chosen.fmt == 1:
            warnings.append("read as format 1, the first glyphbyte alphabet")
    warnings += chosen.warnings
    det.frames, det.patches, det.up, det.direction = chosen.frames, chosen.patches, chosen.up, chosen.d
    return Result(reads=chosen.reads, sequences=sequences, warnings=warnings, detection=det, fmt=chosen.fmt,
                  format_scores={f: r.ll for f, r in results.items()})
