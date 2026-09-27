"""Small CNN for glyph classification, trained on synthetic patches, exported to ONNX.

Four heads on one 64x64 patch:
  icon    16 logits, which icon, read from an upright patch
  dots     4 logits, one per corner dot (top-left first), read from an upright patch
  junk     1 logit, the patch is not a glyph at all, in any rotation
  orient   4 logits, how many quarter turns counter-clockwise the glyph in the patch is
           turned from upright; this is what lets a row that was read upside down or
           sideways be turned back, because every v2 icon but three has a top
"""

from __future__ import annotations

import os
import time

import numpy as np

from .synth import PATCH, load_backdrops, make_junk_patch, make_patch

N_ICONS = 16
N_DOTS = 4                    # one logit per corner dot, bit 3 (top-left) first
N_ORIENT = 4
# box, plus and x look the same after a quarter turn: their patches teach no orientation
SYMMETRIC = frozenset({6, 10, 12})
ROTATED_SHARE = 0.3           # share of glyph patches shown turned by 1 to 3 quarter turns
IGNORE = -100                 # PyTorch's ignore_index: this sample does not train this head

BIG = (32, 64, 128, 192)      # reference model for the Python package
SMALL = (16, 32, 64, 96)      # napplet model: runs in plain JavaScript on a phone


def build_model(channels=BIG):
    import torch.nn as nn

    class Block(nn.Module):
        def __init__(self, cin, cout):
            super().__init__()
            self.net = nn.Sequential(
                nn.Conv2d(cin, cout, 3, padding=1, bias=False), nn.BatchNorm2d(cout), nn.ReLU(inplace=True),
                nn.Conv2d(cout, cout, 3, padding=1, bias=False), nn.BatchNorm2d(cout), nn.ReLU(inplace=True),
                nn.MaxPool2d(2),
            )

        def forward(self, x):
            return self.net(x)

    class GlyphByteNet(nn.Module):
        """1x64x64 normalized patch -> (icon 16, dots 4, junk 1, orient 4) logits."""

        def __init__(self, channels=channels):
            super().__init__()
            c1, c2, c3, c4 = channels
            self.channels = channels
            self.features = nn.Sequential(Block(1, c1), Block(c1, c2), Block(c2, c3), Block(c3, c4))
            self.pool = nn.AdaptiveAvgPool2d(1)
            self.head_sym = nn.Sequential(nn.Dropout(0.2), nn.Linear(c4, N_ICONS))
            self.head_dots = nn.Sequential(nn.Dropout(0.2), nn.Linear(c4, N_DOTS))
            self.head_junk = nn.Sequential(nn.Dropout(0.2), nn.Linear(c4, 1))
            self.head_orient = nn.Sequential(nn.Dropout(0.2), nn.Linear(c4, N_ORIENT))

        def forward(self, x):
            f = self.pool(self.features(x)).flatten(1)
            return self.head_sym(f), self.head_dots(f), self.head_junk(f), self.head_orient(f)

    return GlyphByteNet()


class PatchDataset:
    """Infinite synthetic patches; each worker gets its own RNG stream.

    Returns (x, icon, dots, junk, orient). icon and dots are IGNORE unless the patch is an
    upright glyph; orient is IGNORE for junk and for the symmetric icons."""

    def __init__(self, backdrops_dir: str | None, length: int, seed: int, junk_share: float = 0.15):
        self.backdrops_dir = backdrops_dir
        self.length = length
        self.seed = seed
        self.junk_share = junk_share
        self._backdrops = None

    def __len__(self):
        return self.length

    def __getitem__(self, i):
        import torch
        if self._backdrops is None:
            import cv2
            cv2.setNumThreads(1)      # one thread per data worker: the workers are the parallelism
            self._backdrops = load_backdrops(self.backdrops_dir)
        info = torch.utils.data.get_worker_info()
        wid = info.id if info else 0
        rng = np.random.default_rng([self.seed, wid, i])
        if rng.random() < self.junk_share:
            img, icon, dots, junk, orient = make_junk_patch(rng, self._backdrops), IGNORE, IGNORE, 1.0, IGNORE
        else:
            s = make_patch(rng, self._backdrops)
            k = int(rng.integers(1, 4)) if rng.random() < ROTATED_SHARE else 0
            img = np.ascontiguousarray(np.rot90(s.image, k)) if k else s.image
            icon, dots = (s.icon, s.dots) if k == 0 else (IGNORE, IGNORE)
            junk, orient = 0.0, (IGNORE if s.icon in SYMMETRIC else k)
        img = img if rng.random() < 0.5 else 255 - img   # polarity invariance
        x = torch.from_numpy(img.astype(np.float32) / 255.0).unsqueeze(0)
        return x, icon, dots, junk, orient


def _losses(out, icon, dots, junk, orient):
    import torch
    import torch.nn.functional as F
    li, ld, lj, lo = out
    up = icon != IGNORE
    bits = torch.tensor([8, 4, 2, 1])
    td = ((dots.clamp(min=0)[:, None] & bits) > 0).float()
    loss = F.binary_cross_entropy_with_logits(lj[:, 0], junk.float())
    if up.any():
        loss = loss + F.cross_entropy(li[up], icon[up], label_smoothing=0.05)
        loss = loss + F.binary_cross_entropy_with_logits(ld[up], td[up])
    if (orient != IGNORE).any():
        loss = loss + 0.5 * F.cross_entropy(lo, orient, ignore_index=IGNORE)
    return loss, up, td


def train(out_path: str, backdrops_dir: str | None = None, epochs: int = 8, per_epoch: int = 40000,
          batch: int = 128, workers: int = 12, lr: float = 2e-3, seed: int = 0, log=print, channels=BIG) -> str:
    import torch

    torch.manual_seed(seed)
    model = build_model(channels)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    steps = epochs * (per_epoch // batch)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=lr, total_steps=steps, pct_start=0.15)
    val = torch.utils.data.DataLoader(PatchDataset(backdrops_dir, 4096, seed + 999), batch_size=256,
                                      num_workers=workers)
    step = 0
    for ep in range(epochs):
        ds = PatchDataset(backdrops_dir, per_epoch, seed + ep)
        dl = torch.utils.data.DataLoader(ds, batch_size=batch, shuffle=False, num_workers=workers,
                                         drop_last=True, persistent_workers=False)
        model.train()
        t0, tot, n = time.time(), 0.0, 0
        for x, icon, dots, junk, orient in dl:
            loss, _, _ = _losses(model(x), icon, dots, junk, orient)
            opt.zero_grad(set_to_none=True)
            loss.backward()
            opt.step()
            if step < steps - 1:
                sched.step()
            step += 1
            tot += float(loss.detach()) * len(x)
            n += len(x)
        model.eval()
        c = dict(icon=0, dots=0, byte=0, up=0, junk=0, orient=0, o_n=0, n=0)
        with torch.no_grad():
            for x, icon, dots, junk, orient in val:
                li, ld, lj, lo = model(x)
                _, up, td = _losses((li, ld, lj, lo), icon, dots, junk, orient)
                ok_i = li.argmax(1) == icon
                ok_d = ((ld > 0).float() == td).all(1)
                c["icon"] += int((ok_i & up).sum())
                c["dots"] += int((ok_d & up).sum())
                c["byte"] += int((ok_i & ok_d & up).sum())
                c["up"] += int(up.sum())
                c["junk"] += int(((lj[:, 0] > 0).float() == junk.float()).sum())
                has_o = orient != IGNORE
                c["orient"] += int(((lo.argmax(1) == orient) & has_o).sum())
                c["o_n"] += int(has_o.sum())
                c["n"] += len(x)
        u = max(1, c["up"])
        log(f"epoch {ep + 1}/{epochs} loss {tot / n:.4f} | val icon {c['icon'] / u:.4f} dots {c['dots'] / u:.4f} "
            f"byte {c['byte'] / u:.4f} junk {c['junk'] / c['n']:.4f} orient {c['orient'] / max(1, c['o_n']):.4f} "
            f"| {time.time() - t0:.0f}s")
    # weights first: an export failure must never cost the training run
    torch.save(model.state_dict(), os.path.splitext(out_path)[0] + ".pt")
    export_onnx(model, out_path)
    return out_path


def export_onnx(model, out_path: str) -> None:
    import torch
    model.eval()
    dummy = torch.zeros(1, 1, PATCH, PATCH)
    names = ["icon", "dots", "junk", "orient"]
    torch.onnx.export(model, dummy, out_path, input_names=["patch"], output_names=names,
                      dynamic_axes={"patch": {0: "n"}, **{k: {0: "n"} for k in names}},
                      opset_version=17, dynamo=False)


def export_weights(state_dict_path: str, out_path: str, channels=SMALL) -> dict:
    """Fold batch-norm into the convolutions and write a flat float16 blob plus a JSON
    manifest, for the JavaScript inference in the napplet."""
    import json
    import torch
    sd = torch.load(state_dict_path, map_location="cpu")
    blobs, manifest = [], {"format": 2, "channels": list(channels), "layers": [], "n_icons": N_ICONS,
                           "n_dots": N_DOTS, "n_orient": N_ORIENT, "patch": PATCH}
    offset = 0

    def add(name, arr):
        nonlocal offset
        a = np.ascontiguousarray(arr.detach().numpy().astype(np.float16))
        blobs.append(a)
        manifest["layers"].append({"name": name, "shape": list(a.shape), "offset": offset, "size": int(a.size)})
        offset += int(a.size)

    for bi in range(4):
        for ci, (conv_idx, bn_idx) in enumerate(((0, 1), (3, 4))):
            pre = f"features.{bi}.net."
            w = sd[pre + f"{conv_idx}.weight"]
            g, b, m, v = (sd[pre + f"{bn_idx}.{k}"] for k in ("weight", "bias", "running_mean", "running_var"))
            scale = g / torch.sqrt(v + 1e-5)
            add(f"conv{bi}_{ci}_w", w * scale[:, None, None, None])
            add(f"conv{bi}_{ci}_b", b - m * scale)
    for head in ("sym", "dots", "junk", "orient"):
        add(f"{head}_w", sd[f"head_{head}.1.weight"])
        add(f"{head}_b", sd[f"head_{head}.1.bias"])
    flat = np.concatenate([b.ravel() for b in blobs]).astype(np.float16)
    with open(out_path, "wb") as f:
        f.write(flat.tobytes())
    with open(out_path + ".json", "w") as f:
        json.dump(manifest, f)
    manifest["bytes"] = int(flat.nbytes)
    return manifest
