"""Run the recognizer over a synth directory and score it against truth.jsonl."""

from __future__ import annotations

import json
import os
import time

import numpy as np

from .classify import Classifier
from .pipeline import read_image
from .symbols import SYMBOLS, unpack


def run_bench(directory: str, model: str | None = None, max_sequences: int = 8, limit: int | None = None,
              out: str | None = None) -> dict:
    import cv2
    clf = Classifier(model)
    truth_path = os.path.join(directory, "truth.jsonl")
    with open(truth_path) as f:
        items = [json.loads(line) for line in f if line.strip()]
    if limit:
        items = items[:limit]
    n = len(items)
    exact = topk = 0
    sym_ok = sym_n = 0
    bit_ok = {"icon": 0, "dots": 0}
    frames_found = cells = 0
    confusion = np.zeros((16, 16), int)
    secs = 0.0
    failures = []
    by_bucket: dict[str, list[int]] = {}
    for it in items:
        img = cv2.imread(os.path.join(directory, it["image"]), cv2.IMREAD_COLOR)
        t = time.time()
        res = read_image(img, clf, max_sequences=max_sequences)
        secs += time.time() - t
        truth = bytes.fromhex(it["hex"])
        cells += len(truth)
        got = res.best
        hit = got == truth
        exact += int(hit)
        topk += int(any(b == truth for b, _ in res.sequences))
        # per-symbol scoring when the count matches (otherwise the alignment is unknown)
        if len(res.reads) == len(truth):
            frames_found += len(truth)
            for r, tb in zip(res.reads, truth):
                sym_n += 1
                g, tg = r.glyph, unpack(tb)
                confusion[tg.icon, g.icon] += 1
                sym_ok += int(r.byte == tb)
                bit_ok["icon"] += int(g.icon == tg.icon)
                bit_ok["dots"] += int(g.dots == tg.dots)
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
    ] + [f"| {k} bits | {v:.3f} |" for k, v in rep["bits"].items()] + [
        f"| ms / image | {rep['ms_per_image']:.0f} |", "", "| bucket | exact |", "|---|---|",
    ] + [f"| {k} | {v:.3f} |" for k, v in sorted(rep["buckets"].items())]
    # worst confusions
    conf = confusion.copy()
    np.fill_diagonal(conf, 0)
    pairs = sorted(((conf[i, j], i, j) for i in range(16) for j in range(16) if conf[i, j] > 0), reverse=True)[:8]
    if pairs:
        lines += ["", "| truth | read as | count |", "|---|---|---|"] + [f"| {SYMBOLS[i]} | {SYMBOLS[j]} | {c} |" for c, i, j in pairs]
    rep["markdown"] = "\n".join(lines)
    if out:
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        with open(out, "w") as f:
            json.dump(rep, f, indent=1)
    return rep
