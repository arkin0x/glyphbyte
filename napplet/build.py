"""Bundle the napplet into one self-contained index.html: no imports, no fetches, no external files.

usage: python build.py <weights.bin> <weights.bin.json> [out=dist/index.html]
"""
import base64, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ORDER = ["imgops.js", "geom.js", "nn.js", "detect.js", "pipeline.js", "render.js", "lookup.js", "nip19.js"]


def strip_module(src: str) -> str:
    src = re.sub(r"^import .*?;\s*$", "", src, flags=re.M)
    src = re.sub(r"^export (async function|const|function|let|class) ", r"\1 ", src, flags=re.M)
    return src


def build(weights_path, manifest_path, out_path):
    core = "\n".join(strip_module(open(os.path.join(HERE, "src", f)).read()) for f in ORDER)
    app = open(os.path.join(HERE, "src", "app.js")).read()
    # the icons and frame geometry, generated from glyphbyte/icons.py by scripts/make_spec_assets.py
    shapes = json.load(open(os.path.join(HERE, "..", "spec", "glyphs.json")))
    with open(os.path.join(HERE, "shapes.json"), "w") as f:
        json.dump(shapes, f)
    weights_b64 = base64.b64encode(open(weights_path, "rb").read()).decode()
    manifest = json.load(open(manifest_path))
    html = open(os.path.join(HERE, "index.template.html")).read()
    html = html.replace("/*__CORE__*/", core).replace("/*__SHAPES__*/{}", json.dumps(shapes, separators=(",", ":")))
    html = html.replace("/*__MANIFEST__*/{}", json.dumps(manifest, separators=(",", ":"))).replace("/*__WEIGHTS_B64__*/", weights_b64)
    import subprocess, datetime
    try:
        commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=HERE, text=True).strip()
    except Exception:  # noqa: BLE001
        commit = "unknown"
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M") + " " + commit
    html = html.replace("/*__APP__*/", app).replace("/*__BUILD__*/", stamp)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    open(out_path, "w").write(html)
    # a core-only script for headless tests (no DOM)
    with open(os.path.join(os.path.dirname(out_path), "glyphbyte-core.js"), "w") as f:
        f.write(core + "\nconst SHAPES = " + json.dumps(shapes) + ";\nglobalThis.GlyphByte = { toGray, readImage, detect, describe, unpack, SYMBOLS, loadWeights, classify, SHAPES, lookup, buildFilters, matchPrefix, fetchProfiles, probeRelay, npub, note, nevent, naddr, decodeEntity };\n")
    print(f"wrote {out_path} ({os.path.getsize(out_path) / 1e6:.2f} MB)")


if __name__ == "__main__":
    build(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else os.path.join(HERE, "dist", "index.html"))
