"""Small CNN for glyph classification, trained on synthetic patches, exported to ONNX."""

from __future__ import annotations

import os
import time

import numpy as np

from .synth import PATCH, load_backdrops, make_junk_patch, make_patch

JUNK = 64            # class index for "not a symbol"
N_CLASSES = 65


BIG = (32, 64, 128, 192)      # reference model for the Python package
SMALL = (16, 32, 64, 96)      # napplet model: runs in plain JavaScript on a phone


def build_model(channels=BIG):
    import torch
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

    class SympleNet(nn.Module):
        """1x64x64 normalized patch -> (65 logits: symbol*rotation plus junk, 2 fill logits)."""

        def __init__(self, channels=channels):
            super().__init__()
            c1, c2, c3, c4 = channels
            self.channels = channels
            self.features = nn.Sequential(Block(1, c1), Block(c1, c2), Block(c2, c3), Block(c3, c4))
            self.pool = nn.AdaptiveAvgPool2d(1)
            self.head_sym = nn.Sequential(nn.Dropout(0.2), nn.Linear(c4, N_CLASSES))
            self.head_fill = nn.Sequential(nn.Dropout(0.2), nn.Linear(c4, 2))

        def forward(self, x):
            f = self.pool(self.features(x)).flatten(1)
            return self.head_sym(f), self.head_fill(f)

    return SympleNet()


class PatchDataset:
    """Infinite synthetic patches; each worker gets its own RNG stream."""

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
            self._backdrops = load_backdrops(self.backdrops_dir)
        info = torch.utils.data.get_worker_info()
        wid = info.id if info else 0
        rng = np.random.default_rng([self.seed, wid, i])
        if rng.random() < self.junk_share:
            img, sym_rot, fill = make_junk_patch(rng, self._backdrops), JUNK, 0
        else:
            s = make_patch(rng, self._backdrops)
            img, sym_rot, fill = s.image, s.sym_rot, s.fill
        img = img if rng.random() < 0.5 else 255 - img   # polarity invariance
        x = torch.from_numpy(img.astype(np.float32) / 255.0).unsqueeze(0)
        return x, sym_rot, fill


def train(out_path: str, backdrops_dir: str | None = None, epochs: int = 8, per_epoch: int = 40000,
          batch: int = 128, workers: int = 12, lr: float = 2e-3, seed: int = 0, log=print, channels=BIG) -> str:
    import torch
    import torch.nn.functional as F

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
        t0, tot, n_ok_s, n_ok_f, n = time.time(), 0.0, 0, 0, 0
        for x, ys, yf in dl:
            ls, lf = model(x)
            real = ys != JUNK
            fill_loss = F.cross_entropy(lf[real], yf[real]) if real.any() else ls.sum() * 0
            loss = F.cross_entropy(ls, ys, label_smoothing=0.05) + 0.5 * fill_loss
            opt.zero_grad(set_to_none=True)
            loss.backward()
            opt.step()
            if step < steps - 1:
                sched.step()
            step += 1
            tot += float(loss) * len(x)
            n_ok_s += int((ls.argmax(1) == ys).sum())
            n_ok_f += int(((lf.argmax(1) == yf) | ~real).sum())
            n += len(x)
        model.eval()
        v_ok_s = v_ok_f = v_n = 0
        with torch.no_grad():
            for x, ys, yf in val:
                ls, lf = model(x)
                v_ok_s += int((ls.argmax(1) == ys).sum())
                v_ok_f += int(((lf.argmax(1) == yf) | (ys == JUNK)).sum())
                v_n += len(x)
        log(f"epoch {ep + 1}/{epochs} loss {tot / n:.4f} train sym {n_ok_s / n:.4f} fill {n_ok_f / n:.4f} "
            f"| val sym {v_ok_s / v_n:.4f} fill {v_ok_f / v_n:.4f} | {time.time() - t0:.0f}s")
    # weights first: an export failure must never cost the training run
    torch.save(model.state_dict(), os.path.splitext(out_path)[0] + ".pt")
    export_onnx(model, out_path)
    return out_path


def export_onnx(model, out_path: str) -> None:
    import torch
    model.eval()
    dummy = torch.zeros(1, 1, PATCH, PATCH)
    torch.onnx.export(model, dummy, out_path, input_names=["patch"], output_names=["sym_rot", "fill"],
                      dynamic_axes={"patch": {0: "n"}, "sym_rot": {0: "n"}, "fill": {0: "n"}},
                      opset_version=17, dynamo=False)


def export_weights(state_dict_path: str, out_path: str, channels=SMALL) -> dict:
    """Fold batch-norm into the convolutions and write a flat float16 blob plus a JSON
    manifest, for the JavaScript inference in the napplet."""
    import json
    import torch
    sd = torch.load(state_dict_path, map_location="cpu")
    blobs, manifest = [], {"channels": list(channels), "layers": [], "n_classes": N_CLASSES, "patch": PATCH}
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
    add("sym_w", sd["head_sym.1.weight"])
    add("sym_b", sd["head_sym.1.bias"])
    add("fill_w", sd["head_fill.1.weight"])
    add("fill_b", sd["head_fill.1.bias"])
    flat = np.concatenate([b.ravel() for b in blobs]).astype(np.float16)
    with open(out_path, "wb") as f:
        f.write(flat.tobytes())
    with open(out_path + ".json", "w") as f:
        json.dump(manifest, f)
    manifest["bytes"] = int(flat.nbytes)
    return manifest
