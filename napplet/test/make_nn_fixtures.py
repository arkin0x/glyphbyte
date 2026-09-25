"""Fixtures for nn_check.mjs: PyTorch outputs of the small model on synthetic patches.

usage: python napplet/test/make_nn_fixtures.py <model-small.pt> <out_dir>
writes <out_dir>/fixtures.json and copies nothing else; export the weights to <out_dir> with
glyphbyte.model.export_weights first, then: node napplet/test/nn_check.mjs <out_dir>
"""
import json
import sys

import numpy as np
import torch

from glyphbyte.model import SMALL, build_model
from glyphbyte.synth import load_backdrops, make_patch


def main(pt, out_dir, n=24):
    model = build_model(SMALL)
    model.load_state_dict(torch.load(pt, map_location="cpu"))
    model.eval()
    rng = np.random.default_rng(7)
    bd = load_backdrops("bench/backdrops")
    fx = []
    with torch.no_grad():
        for _ in range(n):
            p = make_patch(rng, bd).image.astype(np.float32) / 255.0
            li, ld = model(torch.from_numpy(p)[None, None])
            sym = torch.softmax(li, 1)[0].numpy()
            fx.append({"patch": p.ravel().round(5).tolist(), "icon": (sym[:16] / sym[:16].sum()).tolist(),
                       "junk": float(sym[16]), "dots": torch.sigmoid(ld)[0].numpy().tolist()})
    json.dump(fx, open(f"{out_dir}/fixtures.json", "w"))
    print(f"wrote {n} fixtures to {out_dir}/fixtures.json")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
