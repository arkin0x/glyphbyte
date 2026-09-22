"""Small CNN for glyph classification, trained on synthetic patches, exported to ONNX."""

from __future__ import annotations

import os
import time

import numpy as np

from .synth import PATCH, load_backdrops, make_patch


def build_model():
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
        """1x64x64 normalized patch -> (64 symbol*rotation logits, 2 fill logits)."""

        def __init__(self):
            super().__init__()
            self.features = nn.Sequential(Block(1, 32), Block(32, 64), Block(64, 128), Block(128, 192))
            self.pool = nn.AdaptiveAvgPool2d(1)
            self.head_sym = nn.Sequential(nn.Dropout(0.2), nn.Linear(192, 64))
            self.head_fill = nn.Sequential(nn.Dropout(0.2), nn.Linear(192, 2))

        def forward(self, x):
            f = self.pool(self.features(x)).flatten(1)
            return self.head_sym(f), self.head_fill(f)

    return SympleNet()


class PatchDataset:
    """Infinite synthetic patches; each worker gets its own RNG stream."""

    def __init__(self, backdrops_dir: str | None, length: int, seed: int):
        self.backdrops_dir = backdrops_dir
        self.length = length
        self.seed = seed
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
        s = make_patch(rng, self._backdrops)
        img = s.image if rng.random() < 0.5 else 255 - s.image   # polarity invariance
        x = torch.from_numpy(img.astype(np.float32) / 255.0).unsqueeze(0)
        return x, s.sym_rot, s.fill


def train(out_path: str, backdrops_dir: str | None = None, epochs: int = 8, per_epoch: int = 40000,
          batch: int = 128, workers: int = 12, lr: float = 2e-3, seed: int = 0, log=print) -> str:
    import torch
    import torch.nn.functional as F

    torch.manual_seed(seed)
    model = build_model()
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
            loss = F.cross_entropy(ls, ys, label_smoothing=0.05) + 0.5 * F.cross_entropy(lf, yf)
            opt.zero_grad(set_to_none=True)
            loss.backward()
            opt.step()
            if step < steps - 1:
                sched.step()
            step += 1
            tot += float(loss) * len(x)
            n_ok_s += int((ls.argmax(1) == ys).sum())
            n_ok_f += int((lf.argmax(1) == yf).sum())
            n += len(x)
        model.eval()
        v_ok_s = v_ok_f = v_n = 0
        with torch.no_grad():
            for x, ys, yf in val:
                ls, lf = model(x)
                v_ok_s += int((ls.argmax(1) == ys).sum())
                v_ok_f += int((lf.argmax(1) == yf).sum())
                v_n += len(x)
        log(f"epoch {ep + 1}/{epochs} loss {tot / n:.4f} train sym {n_ok_s / n:.4f} fill {n_ok_f / n:.4f} "
            f"| val sym {v_ok_s / v_n:.4f} fill {v_ok_f / v_n:.4f} | {time.time() - t0:.0f}s")
    export_onnx(model, out_path)
    torch.save(model.state_dict(), os.path.splitext(out_path)[0] + ".pt")
    return out_path


def export_onnx(model, out_path: str) -> None:
    import torch
    model.eval()
    dummy = torch.zeros(1, 1, PATCH, PATCH)
    torch.onnx.export(model, dummy, out_path, input_names=["patch"], output_names=["sym_rot", "fill"],
                      dynamic_axes={"patch": {0: "n"}, "sym_rot": {0: "n"}, "fill": {0: "n"}},
                      opset_version=17, dynamo=False)
