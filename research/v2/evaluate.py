"""Machine side of the comparison: how learnable and how robust is each glyph set?

For every set, the same small CNN is trained with the same budget on the same
kind of synthetic photos (all four media mixed), then tested per medium on
fresh photos. Patches are rectified with noisy corners, the way a detector
would hand them over. Output: out/eval.json and a printed table.

Usage: python evaluate.py [--sets ring,star,...] [--train 80000] [--epochs 6]
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))

from draw import MEDIA, photo_of_glyph  # noqa: E402
from sets import BITS  # noqa: E402
from glyphbyte.synth import load_backdrops, normalize_patch  # noqa: E402

P = 48
MARGIN = 0.12
MARGINS = {"sun": 0.22}   # the sun's rays reach 1.5 radii out; keep them in the patch
_BD = None


def _bd():
    global _BD
    if _BD is None:
        _BD = load_backdrops(str(HERE.parents[1] / "bench" / "backdrops"))
    return _BD


def detector_noise(q, cell, rng):
    """Corners as a detector would report them: jittered, scaled, slightly rotated."""
    q = q + rng.normal(0, 0.035 * cell, size=(4, 2))
    c = q.mean(axis=0)
    q = c + (q - c) * rng.uniform(0.92, 1.12)
    if rng.random() < 0.5:
        a = rng.normal(0, math.radians(5))
        R = np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])
        q = c + (q - c) @ R.T
    return q


def patch(args):
    set_name, byte, medium, seed, hand = args
    rng = np.random.default_rng(seed)
    gray, q, light, cell = photo_of_glyph(set_name, byte, medium, rng, _bd(), hand)
    q = detector_noise(q, np.linalg.norm(q[1] - q[0]), rng)
    m = P * MARGINS.get(set_name, MARGIN)
    H = cv2.getPerspectiveTransform(q.astype(np.float32), np.float32([[m, m], [P - m, m], [P - m, P - m], [m, P - m]]))
    p = cv2.warpPerspective(gray, H, (P, P), flags=cv2.INTER_AREA, borderMode=cv2.BORDER_REPLICATE)
    return normalize_patch(p, light), byte


def make_data(set_name, n, seed, media=None, hand=None, pool=None):
    rng = np.random.default_rng(seed)
    jobs = []
    for i in range(n):
        m = media if media else MEDIA[i % len(MEDIA)]
        jobs.append((set_name, int(rng.integers(0, 2 ** BITS[set_name])), m, int(rng.integers(0, 2**62)), hand))
    res = pool.map(patch, jobs, chunksize=64)
    X = np.stack([r[0] for r in res]).astype(np.uint8)
    y = np.array([r[1] for r in res], np.int64)
    return X, y


def build_model(n_out=256):
    import torch.nn as nn

    def block(i, o):
        return nn.Sequential(nn.Conv2d(i, o, 3, padding=1, bias=False), nn.BatchNorm2d(o), nn.ReLU(),
                             nn.Conv2d(o, o, 3, padding=1, bias=False), nn.BatchNorm2d(o), nn.ReLU(),
                             nn.MaxPool2d(2))
    return nn.Sequential(block(1, 24), block(24, 48), block(48, 96), block(96, 128),
                         nn.AdaptiveAvgPool2d(1), nn.Flatten(), nn.Dropout(0.2), nn.Linear(128, n_out))


def train(X, y, epochs, seed=0, bits=None):
    """256-way softmax, or with `bits` one sigmoid per bit (for sets wider than a byte)."""
    import torch
    torch.manual_seed(seed)
    torch.set_num_threads(16)
    model = build_model(bits or 256)
    opt = torch.optim.AdamW(model.parameters(), 2e-3, weight_decay=1e-4)
    n = len(X)
    steps = epochs * math.ceil(n / 256)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, 3e-3, total_steps=steps)
    Xt = torch.from_numpy(X).float().div(255).unsqueeze(1)
    yt = torch.from_numpy(y)
    model.train()
    for ep in range(epochs):
        perm = torch.randperm(n)
        tot, correct = 0.0, 0
        for i in range(0, n, 256):
            idx = perm[i:i + 256]
            xb = Xt[idx]
            # cheap extra augmentation: small shifts
            if True:
                dx, dy = np.random.randint(-2, 3, 2)
                xb = torch.roll(xb, shifts=(int(dy), int(dx)), dims=(2, 3))
            out = model(xb)
            if bits:
                tgt = ((yt[idx][:, None] >> torch.arange(bits)) & 1).float()
                loss = torch.nn.functional.binary_cross_entropy_with_logits(out, tgt)
            else:
                loss = torch.nn.functional.cross_entropy(out, yt[idx], label_smoothing=0.05)
            opt.zero_grad()
            loss.backward()
            opt.step()
            sched.step()
            tot += loss.item() * len(idx)
            correct += (decode(out, bits) == yt[idx]).sum().item()
        print(f"    epoch {ep + 1}/{epochs} loss {tot / n:.3f} train acc {correct / n:.3f}", flush=True)
    model.eval()
    return model


def decode(out, bits):
    import torch
    if bits:
        return ((out > 0).long() << torch.arange(bits)).sum(1)
    return out.argmax(1)


def predict(model, X, bits=None):
    import torch
    with torch.no_grad():
        Xt = torch.from_numpy(X).float().div(255).unsqueeze(1)
        out = torch.cat([model(Xt[i:i + 1024]) for i in range(0, len(Xt), 1024)])
    return decode(out, bits).numpy()


def bit_errors(pred, y):
    x = np.bitwise_xor(pred, y)
    return float(np.mean([bin(int(v)).count("1") for v in x]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sets", default="v1,ring,star,dice,tally")
    ap.add_argument("--train", type=int, default=80000)
    ap.add_argument("--test", type=int, default=2048)
    ap.add_argument("--epochs", type=int, default=6)
    ap.add_argument("--out", default=str(HERE / "out" / "eval.json"))
    a = ap.parse_args()
    results = json.load(open(a.out)) if os.path.exists(a.out) else {}
    with Pool(15) as pool:
        for s in a.sets.split(","):
            t0 = time.time()
            print(f"== {s}: generating {a.train} training photos", flush=True)
            X, y = make_data(s, a.train, seed=1000, pool=pool)
            print(f"   {time.time() - t0:.0f}s; training", flush=True)
            bits = BITS[s] if BITS[s] > 8 else None
            model = train(X, y, a.epochs, bits=bits)
            r = {"train_s": round(time.time() - t0), "media": {}}
            for m in MEDIA + ["hard"]:
                if m == "hard":   # the sloppiest hand, any medium
                    Xs, ys = make_data(s, a.test, seed=99, hand=1.0, pool=pool)
                else:
                    Xs, ys = make_data(s, a.test, seed=5 + MEDIA.index(m), media=m, pool=pool)
                pred = predict(model, Xs, bits)
                acc = float((pred == ys).mean())
                conf = {}
                for p_, t_ in zip(pred, ys):
                    if p_ != t_:
                        k_ = f"{t_:03x}>{p_:03x}" if bits else f"{t_:02x}>{p_:02x}"
                        conf[k_] = conf.get(k_, 0) + 1
                top = sorted(conf.items(), key=lambda kv: -kv[1])[:8]
                r["media"][m] = {"acc": round(acc, 4), "bits_wrong_per_glyph": round(bit_errors(pred, ys), 4),
                                 "top_confusions": top}
                print(f"   {m:7s} acc {acc:.3f}  bit errors/glyph {bit_errors(pred, ys):.3f}  {top[:4]}", flush=True)
            results[s] = r
            json.dump(results, open(a.out, "w"), indent=1)
            import torch
            torch.save(model.state_dict(), HERE / "out" / f"model_{s}.pt")


if __name__ == "__main__":
    main()
