"""Run the recognizer over a synth directory and score it against truth.jsonl."""

from __future__ import annotations

import json
import os
import time

import numpy as np

from . import v1
from .classify import load_classifiers
from .pipeline import read_image
from .symbols import SYMBOLS, unpack

# per-glyph parts compared when the format was read right
_PARTS = {
    2: lambda b: {"icon": b >> 4, "dots": b & 15},
    1: lambda b: {"symbol": b >> 4, "rotation": (b >> 2) & 3, "fill": (b >> 1) & 1, "frame": b & 1},
}


def run_bench(directory: str, model: str | None = None, max_sequences: int = 8, limit: int | None = None,
              out: str | None = None, model_v1: str | None = None, fmt: int | str = "auto",
              truth_format: int = 2) -> dict:
    """truth_format is the format of scenes whose truth.jsonl does not say (suites made before
    format v2 was added have no "format" field and are format 1)."""
    import cv2
    clfs = load_classifiers(model, model_v1)
    truth_path = os.path.join(directory, "truth.jsonl")
    with open(truth_path) as f:
        items = [json.loads(line) for line in f if line.strip()]
    if limit:
        items = items[:limit]
    n = len(items)
    exact = topk = 0
    sym_ok = sym_n = 0
    bit_ok: dict[str, int] = {}
    fmt_ok = 0
    frames_found = cells = 0
    confusion = np.zeros((16, 16), int)
    secs = 0.0
    failures = []
    by_bucket: dict[str, list[int]] = {}
    for it in items:
        img = cv2.imread(os.path.join(directory, it["image"]), cv2.IMREAD_COLOR)
        t = time.time()
        res = read_image(img, clfs, max_sequences=max_sequences, fmt=fmt)
        t_fmt = int(it.get("format", truth_format))
        fmt_ok += int(res.fmt == t_fmt)
        secs += time.time() - t
        truth = bytes.fromhex(it["hex"])
        cells += len(truth)
        got = res.best
        hit = got == truth
        exact += int(hit)
        topk += int(any(r.bytes == truth for r in res.sequences))
        # per-symbol scoring when the count matches (otherwise the alignment is unknown)
        if len(res.reads) == len(truth):
            frames_found += len(truth)
            for r, tb in zip(res.reads, truth):
                sym_n += 1
                confusion[tb >> 4, r.byte >> 4] += 1
                sym_ok += int(r.byte == tb)
                if res.fmt == t_fmt:
                    got_p, true_p = _PARTS[t_fmt](r.byte), _PARTS[t_fmt](tb)
                    for k in true_p:
                        bit_ok[k] = bit_ok.get(k, 0) + int(got_p[k] == true_p[k])
        else:
            frames_found += min(len(res.reads), len(truth))
        hb = "hand<0.5" if it.get("hand", 0) < 0.5 else "hand>=0.5"
        pb = "persp<0.1" if it.get("perspective", 0) < 0.1 else "persp>=0.1"
        for k in (hb, pb, "light_ink" if it.get("light_ink") else "dark_ink"):
            by_bucket.setdefault(k, []).append(int(hit))
        if not hit:
            failures.append({"image": it["image"], "truth": it["hex"], "got": got.hex(),
                             "n_found": len(res.reads), "warnings": res.warnings})
    rep = {
        "n": n, "cells": cells, "exact": exact / max(n, 1), "in_candidates": topk / max(n, 1),
        "frame_recall": frames_found / max(cells, 1),
        "symbol_byte_acc": sym_ok / max(sym_n, 1),
        "format_right": fmt_ok / max(n, 1),
        "bits": {k: v / max(sym_n, 1) for k, v in bit_ok.items()},
        "buckets": {k: float(np.mean(v)) for k, v in by_bucket.items()},
        "ms_per_image": 1000 * secs / max(n, 1),
        "confusion": confusion.tolist(),
        "failures": failures,
    }
    lines = [
        f"# glyphbyte bench: {directory}", "",
        f"| metric | value |", f"|---|---|",
        f"| scenes | {n} |", f"| symbols | {cells} |",
        f"| whole sequence exact (top-1) | {rep['exact']:.3f} |",
        f"| truth among candidate sequences | {rep['in_candidates']:.3f} |",
        f"| frames found | {rep['frame_recall']:.3f} |",
        f"| symbol byte accuracy (aligned) | {rep['symbol_byte_acc']:.3f} |",
        f"| format read right | {rep['format_right']:.3f} |",
    ] + [f"| {k} bits | {v:.3f} |" for k, v in rep["bits"].items()] + [
        f"| ms / image | {rep['ms_per_image']:.0f} |", "", "| bucket | exact |", "|---|---|",
    ] + [f"| {k} | {v:.3f} |" for k, v in sorted(rep["buckets"].items())]
    # worst confusions
    conf = confusion.copy()
    np.fill_diagonal(conf, 0)
    pairs = sorted(((conf[i, j], i, j) for i in range(16) for j in range(16) if conf[i, j] > 0), reverse=True)[:8]
    names = v1.SYMBOLS if truth_format == 1 else SYMBOLS
    if pairs:
        lines += ["", "| truth | read as | count |", "|---|---|---|"] + [f"| {names[i]} | {names[j]} | {c} |" for c, i, j in pairs]
    rep["markdown"] = "\n".join(lines)
    if out:
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        with open(out, "w") as f:
            json.dump(rep, f, indent=1)
    return rep
