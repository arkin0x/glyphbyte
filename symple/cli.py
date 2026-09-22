"""symple command line: decode photos, encode bytes, make sheets, synthesize and benchmark."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np

from . import __version__
from .symbols import SYMBOLS, unpack


def _cv2():
    import cv2
    return cv2


def cmd_decode(a):
    cv2 = _cv2()
    from .pipeline import read_image
    from .classify import Classifier
    clf = Classifier(a.model)
    for path in a.image:
        img = cv2.imread(path, cv2.IMREAD_COLOR)
        if img is None:
            print(f"{path}: cannot read image", file=sys.stderr)
            continue
        t = time.time()
        res = read_image(img, clf, max_sequences=a.max_sequences, fork_ratio=a.fork_ratio)
        dt = time.time() - t
        if a.debug:
            from .detect import draw_debug
            cv2.imwrite(a.debug, draw_debug(res.detection))
        if a.json:
            d = res.to_dict()
            d["image"] = path
            d["seconds"] = round(dt, 3)
            print(json.dumps(d))
            continue
        if not res.sequences:
            print(f"{path}: {'; '.join(res.warnings)}")
            continue
        print(res.best.hex())
        if a.verbose:
            for b, p in res.sequences:
                print(f"  {b.hex()}  p={p:.3f}", file=sys.stderr)
            for r in res.reads:
                alts = ", ".join(f"{unpack(b).describe()} ({p:.2f})" for b, p in r.candidates[1:])
                print(f"  [{r.index}] {r.glyph.describe()} ({r.confidence:.2f})" + (f"  or {alts}" if alts else ""), file=sys.stderr)
            for w in res.warnings:
                print(f"  ! {w}", file=sys.stderr)


def cmd_encode(a):
    cv2 = _cv2()
    from .render import render_row
    data = bytes.fromhex(a.hex)
    rng = np.random.default_rng(a.seed)
    row = render_row(data, cell=a.cell, hand=a.hand, rng=rng, baseline=not a.no_baseline)
    cv2.imwrite(a.out, row.canvas)
    for i, b in enumerate(data):
        print(f"[{i}] {b:02x}  {unpack(b).describe()}")
    print(f"wrote {a.out}")


def cmd_sheet(a):
    cv2 = _cv2()
    from .render import render_sheet
    cv2.imwrite(a.out, render_sheet(cell=a.cell, hand=a.hand, seed=a.seed))
    print(f"wrote {a.out}: rows are symbols 0..15 ({', '.join(SYMBOLS)}); columns are rotations 0,90,180,270 outline then filled")


def cmd_synth(a):
    cv2 = _cv2()
    from .synth import load_backdrops, make_scene
    os.makedirs(a.out, exist_ok=True)
    bd = load_backdrops(a.backdrops)
    rng = np.random.default_rng(a.seed)
    with open(os.path.join(a.out, "truth.jsonl"), "w") as f:
        for i in range(a.n):
            sc = make_scene(rng, bd, n_bytes=a.bytes, hand=a.hand, perspective=a.perspective, baseline=not a.no_baseline)
            name = f"scene_{i:04d}.jpg"
            cv2.imwrite(os.path.join(a.out, name), sc.image, [cv2.IMWRITE_JPEG_QUALITY, 92])
            f.write(json.dumps({"image": name, "hex": sc.data.hex(), "hand": round(sc.hand, 3),
                                "perspective": round(sc.perspective, 3), "light_ink": sc.light_ink,
                                "cells": [{"byte": c["byte"], "corners": np.round(c["corners"], 1).tolist()} for c in sc.cells]}) + "\n")
    print(f"wrote {a.n} scenes to {a.out} (backdrops: {len(bd)} photos + procedural)")


def cmd_bench(a):
    from .bench import run_bench
    report = run_bench(a.dir, model=a.model, max_sequences=a.max_sequences, limit=a.limit, out=a.out)
    print(report["markdown"])


def cmd_train(a):
    from .model import train
    train(a.out, backdrops_dir=a.backdrops, epochs=a.epochs, per_epoch=a.per_epoch, batch=a.batch,
          workers=a.workers, seed=a.seed)
    print(f"wrote {a.out}")


def cmd_backdrops(a):
    import urllib.request
    os.makedirs(a.out, exist_ok=True)
    for i in range(a.n):
        url = f"https://picsum.photos/seed/symple{i + 1}/{a.width}/{a.height}"
        dst = os.path.join(a.out, f"picsum_{i + 1}.jpg")
        try:
            urllib.request.urlretrieve(url, dst)
        except Exception as e:  # noqa: BLE001
            print(f"{url}: {e}", file=sys.stderr)
    print(f"downloaded to {a.out}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="symple", description="hand-drawn symbols to bytes")
    p.add_argument("--version", action="version", version=f"symple-cli {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("decode", help="read the symbols in a photo and print the bytes as hex")
    d.add_argument("image", nargs="+")
    d.add_argument("--json", action="store_true", help="full result with candidates and warnings")
    d.add_argument("-v", "--verbose", action="store_true", help="show alternatives and warnings on stderr")
    d.add_argument("--max-sequences", type=int, default=8)
    d.add_argument("--fork-ratio", type=float, default=0.2, help="keep an alternative when it is at least this fraction as likely as the best")
    d.add_argument("--model", default=None, help="path to an ONNX model (default: bundled)")
    d.add_argument("--debug", default=None, help="write a detection overlay image here")
    d.set_defaults(fn=cmd_decode)

    e = sub.add_parser("encode", help="render bytes as a row of symbols")
    e.add_argument("hex")
    e.add_argument("--out", default="symple-row.png")
    e.add_argument("--cell", type=int, default=120)
    e.add_argument("--hand", type=float, default=0.0, help="0 clean, 1 fully hand-drawn style")
    e.add_argument("--seed", type=int, default=0)
    e.add_argument("--no-baseline", action="store_true")
    e.set_defaults(fn=cmd_encode)

    s = sub.add_parser("sheet", help="render the reference sheet of all symbols")
    s.add_argument("--out", default="symple-sheet.png")
    s.add_argument("--cell", type=int, default=90)
    s.add_argument("--hand", type=float, default=0.0)
    s.add_argument("--seed", type=int, default=0)
    s.set_defaults(fn=cmd_sheet)

    y = sub.add_parser("synth", help="generate a test suite of photo-like scenes with ground truth")
    y.add_argument("--out", required=True)
    y.add_argument("--n", type=int, default=200)
    y.add_argument("--backdrops", default=None, help="directory of photos to draw on")
    y.add_argument("--bytes", type=int, default=None, help="fixed sequence length (default random 2..8)")
    y.add_argument("--hand", type=float, default=None)
    y.add_argument("--perspective", type=float, default=None)
    y.add_argument("--no-baseline", action="store_true")
    y.add_argument("--seed", type=int, default=0)
    y.set_defaults(fn=cmd_synth)

    b = sub.add_parser("bench", help="decode a synth directory and report accuracy")
    b.add_argument("dir")
    b.add_argument("--model", default=None)
    b.add_argument("--max-sequences", type=int, default=8)
    b.add_argument("--limit", type=int, default=None)
    b.add_argument("--out", default=None, help="write the JSON report here")
    b.set_defaults(fn=cmd_bench)

    t = sub.add_parser("train", help="train the classifier on synthetic patches (needs torch)")
    t.add_argument("--out", default="symple/data/model.onnx")
    t.add_argument("--backdrops", default=None)
    t.add_argument("--epochs", type=int, default=8)
    t.add_argument("--per-epoch", type=int, default=40000)
    t.add_argument("--batch", type=int, default=128)
    t.add_argument("--workers", type=int, default=8)
    t.add_argument("--seed", type=int, default=0)
    t.set_defaults(fn=cmd_train)

    k = sub.add_parser("backdrops", help="download public-domain photos from picsum.photos for synth/bench")
    k.add_argument("--out", default="bench/backdrops")
    k.add_argument("--n", type=int, default=48)
    k.add_argument("--width", type=int, default=1200)
    k.add_argument("--height", type=int, default=900)
    k.set_defaults(fn=cmd_backdrops)

    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
