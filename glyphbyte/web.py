"""Web app: bytes to glyphs, photo to bytes. `glyphbyte serve` runs it; deploy/ has the containers."""

from __future__ import annotations

import base64
import io
from importlib import resources

import cv2
import numpy as np
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response

from . import __version__
from . import v1
from .classify import load_classifiers
from .detect import draw_debug
from .pipeline import read_image
from .render import render_row, render_sheet
from .symbols import SYMBOLS, unpack


def create_app(model_path: str | None = None) -> FastAPI:
    app = FastAPI(title="glyphbyte", version=__version__)
    state = {"clfs": None, "model_path": model_path}

    def clfs():
        if state["clfs"] is None:
            state["clfs"] = load_classifiers(state["model_path"])
        return state["clfs"]

    def check_format(fmt: int) -> int:
        if fmt not in (1, 2):
            raise HTTPException(400, "format is 1 or 2")
        return fmt

    @app.get("/", response_class=HTMLResponse)
    def index():
        return resources.files("glyphbyte.static").joinpath("index.html").read_text()

    @app.get("/api/symbols")
    def symbols():
        return {"default_format": 2, "formats": {
            "2": {"symbols": SYMBOLS, "layout": "high nibble icon; low nibble corner dots: top-left 8, top-right 4, bottom-right 2, bottom-left 1"},
            "1": {"symbols": v1.SYMBOLS, "layout": "high nibble symbol, bits 3..2 rotation cw quarter turns, bit 1 fill, bit 0 frame (0 square, 1 circle)"}}}

    @app.get("/api/describe")
    def describe(hex: str = Query(..., min_length=2), format: int = 2):
        fmt = check_format(format)
        try:
            data = bytes.fromhex(hex)
        except ValueError:
            raise HTTPException(400, "hex expected")
        return {"hex": data.hex(), "format": fmt,
                "symbols": [{"index": i, "byte": b, "hex": f"{b:02x}", **_glyph(b, fmt)} for i, b in enumerate(data)]}

    @app.get("/api/encode.png")
    def encode_png(hex: str = Query(..., min_length=2), cell: int = 140, hand: float = 0.0, seed: int = 0, format: int = 2):
        fmt = check_format(format)
        try:
            data = bytes.fromhex(hex)
        except ValueError:
            raise HTTPException(400, "hex expected")
        if len(data) > 32:
            raise HTTPException(400, "at most 32 bytes")
        row = render_row(data, cell=max(40, min(cell, 300)), hand=max(0.0, min(hand, 1.0)), rng=np.random.default_rng(seed), fmt=fmt)
        ok, png = cv2.imencode(".png", row.canvas)
        return Response(png.tobytes(), media_type="image/png")

    @app.get("/api/sheet.png")
    def sheet_png(cell: int = 80, format: int = 2):
        ok, png = cv2.imencode(".png", render_sheet(cell=max(30, min(cell, 160)), fmt=check_format(format)))
        return Response(png.tobytes(), media_type="image/png")

    @app.post("/api/decode")
    async def decode(image: UploadFile = File(...), debug: bool = False, max_sequences: int = 8, fork_ratio: float = 0.2,
                     format: str = "auto"):
        fmt = format if format == "auto" else check_format(int(format))
        raw = await image.read()
        arr = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
        if arr is None:
            raise HTTPException(400, "not an image")
        res = read_image(arr, clfs(), max_sequences=max(1, min(max_sequences, 32)), fork_ratio=max(0.01, min(fork_ratio, 1.0)),
                         fmt=fmt)
        out = res.to_dict()
        out["symbols"] = [{**s, **_glyph(s["byte"], res.fmt)} for s in out["symbols"]]
        if debug and res.detection is not None:
            ok, png = cv2.imencode(".png", draw_debug(res.detection))
            out["debug_png"] = "data:image/png;base64," + base64.b64encode(png.tobytes()).decode()
        return JSONResponse(out)

    return app


def _glyph(b: int, fmt: int = 2) -> dict:
    if fmt == 1:
        g1 = v1.unpack(b)
        return {"name": g1.name, "rotation": g1.rotation * 90, "fill": "filled" if g1.fill else "outline",
                "frame": "circle" if g1.frame else "square", "text": g1.describe()}
    g = unpack(b)
    return {"name": g.name, "icon": g.icon, "dots": g.dots, "dot_corners": g.dot_corners(), "text": g.describe()}


def serve(host: str = "127.0.0.1", port: int = 8765, model_path: str | None = None):
    import uvicorn
    uvicorn.run(create_app(model_path), host=host, port=port)
