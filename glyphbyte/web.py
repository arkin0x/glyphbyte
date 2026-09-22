"""Web app: bytes to symbols, photo to bytes. `glyphbyte serve` runs it; deploy/ has the containers."""

from __future__ import annotations

import base64
import io
from importlib import resources

import cv2
import numpy as np
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response

from . import __version__
from .classify import Classifier
from .detect import draw_debug
from .pipeline import read_image
from .render import render_row, render_sheet
from .symbols import SYMBOLS, unpack


def create_app(model_path: str | None = None) -> FastAPI:
    app = FastAPI(title="glyphbyte", version=__version__)
    state = {"clf": None, "model_path": model_path}

    def clf() -> Classifier:
        if state["clf"] is None:
            state["clf"] = Classifier(state["model_path"])
        return state["clf"]

    @app.get("/", response_class=HTMLResponse)
    def index():
        return resources.files("glyphbyte.static").joinpath("index.html").read_text()

    @app.get("/api/symbols")
    def symbols():
        return {"symbols": SYMBOLS, "layout": "high nibble symbol, bits 3..2 rotation cw quarter turns, bit 1 fill, bit 0 frame (0 square, 1 circle)"}

    @app.get("/api/describe")
    def describe(hex: str = Query(..., min_length=2)):
        try:
            data = bytes.fromhex(hex)
        except ValueError:
            raise HTTPException(400, "hex expected")
        return {"hex": data.hex(), "symbols": [{"index": i, "byte": b, "hex": f"{b:02x}", **_glyph(b)} for i, b in enumerate(data)]}

    @app.get("/api/encode.png")
    def encode_png(hex: str = Query(..., min_length=2), cell: int = 140, hand: float = 0.0, seed: int = 0):
        try:
            data = bytes.fromhex(hex)
        except ValueError:
            raise HTTPException(400, "hex expected")
        if len(data) > 32:
            raise HTTPException(400, "at most 32 bytes")
        row = render_row(data, cell=max(40, min(cell, 300)), hand=max(0.0, min(hand, 1.0)), rng=np.random.default_rng(seed))
        ok, png = cv2.imencode(".png", row.canvas)
        return Response(png.tobytes(), media_type="image/png")

    @app.get("/api/sheet.png")
    def sheet_png(cell: int = 80):
        ok, png = cv2.imencode(".png", render_sheet(cell=max(30, min(cell, 160))))
        return Response(png.tobytes(), media_type="image/png")

    @app.post("/api/decode")
    async def decode(image: UploadFile = File(...), debug: bool = False, max_sequences: int = 8, fork_ratio: float = 0.2):
        raw = await image.read()
        arr = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
        if arr is None:
            raise HTTPException(400, "not an image")
        res = read_image(arr, clf(), max_sequences=max(1, min(max_sequences, 32)), fork_ratio=max(0.01, min(fork_ratio, 1.0)))
        out = res.to_dict()
        out["symbols"] = [{**s, **_glyph(s["byte"])} for s in out["symbols"]]
        if debug and res.detection is not None:
            ok, png = cv2.imencode(".png", draw_debug(res.detection))
            out["debug_png"] = "data:image/png;base64," + base64.b64encode(png.tobytes()).decode()
        return JSONResponse(out)

    return app


def _glyph(b: int) -> dict:
    g = unpack(b)
    return {"name": g.name, "rotation": g.rotation * 90, "fill": "filled" if g.fill else "outline",
            "frame": "circle" if g.frame else "square", "text": g.describe()}


def serve(host: str = "127.0.0.1", port: int = 8765, model_path: str | None = None):
    import uvicorn
    uvicorn.run(create_app(model_path), host=host, port=port)
