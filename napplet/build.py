"""Bundle the napplet into one self-contained index.html: no imports, no fetches, no external files.

usage: python build.py <weights.bin> <weights.bin.json> [out=dist/index.html] [weights-v1.bin weights-v1.bin.json]
The format 1 model defaults to weights-v1.bin next to this file: the page reads both formats.
"""
import base64, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ORDER = ["imgops.js", "geom.js", "nn.js", "detect.js", "pipeline.js", "render.js", "lookup.js", "nip19.js"]


def strip_module(src: str) -> str:
    src = re.sub(r"^import .*?;\s*$", "", src, flags=re.M)
    src = re.sub(r"^export (async function|const|function|let|class) ", r"\1 ", src, flags=re.M)
    return src


def build(weights_path, manifest_path, out_path, weights_v1=None, manifest_v1=None):
    weights_v1 = weights_v1 or os.path.join(HERE, "weights-v1.bin")
    manifest_v1 = manifest_v1 or os.path.join(HERE, "weights-v1.bin.json")
    core = "\n".join(strip_module(open(os.path.join(HERE, "src", f)).read()) for f in ORDER)
    app = open(os.path.join(HERE, "src", "app.js")).read()
    # the icons and frame geometry, generated from glyphbyte/icons.py by scripts/make_spec_assets.py
    shapes = json.load(open(os.path.join(HERE, "..", "spec", "glyphs.json")))
    with open(os.path.join(HERE, "shapes.json"), "w") as f:
        json.dump(shapes, f)
    # format 1's pictograms, so v1 rows can still be drawn
    shapes_v1 = json.load(open(os.path.join(HERE, "..", "spec", "glyphs-v1.json")))
    with open(os.path.join(HERE, "shapes-v1.json"), "w") as f:
        json.dump(shapes_v1, f)
    weights_b64 = base64.b64encode(open(weights_path, "rb").read()).decode()
    manifest = json.load(open(manifest_path))
    weights_v1_b64 = base64.b64encode(open(weights_v1, "rb").read()).decode()
    man_v1 = json.load(open(manifest_v1))
    html = open(os.path.join(HERE, "index.template.html")).read()
    html = html.replace("/*__CORE__*/", core).replace("/*__SHAPES__*/{}", json.dumps(shapes, separators=(",", ":")))
    html = html.replace("/*__MANIFEST__*/{}", json.dumps(manifest, separators=(",", ":"))).replace("/*__WEIGHTS_B64__*/", weights_b64)
    html = html.replace("/*__SHAPES_V1__*/[]", json.dumps(shapes_v1, separators=(",", ":")))
    html = html.replace("/*__MANIFEST_V1__*/{}", json.dumps(man_v1, separators=(",", ":"))).replace("/*__WEIGHTS_V1_B64__*/", weights_v1_b64)
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
        f.write(core + "\nconst SHAPES = " + json.dumps(shapes) + ";\nconst SHAPES_V1 = " + json.dumps(shapes_v1) +
                ";\nglobalThis.GlyphByte = { toGray, readImage, detect, describe, unpack, SYMBOLS, SYMBOLS_V1, turnedV1, loadWeights, classify, modelFormat, SHAPES, SHAPES_V1, lookup, buildFilters, matchPrefix, fetchProfiles, probeRelay, npub, note, nevent, naddr, decodeEntity };\n")
    print(f"wrote {out_path} ({os.path.getsize(out_path) / 1e6:.2f} MB)")


if __name__ == "__main__":
    a = sys.argv[1:]
    build(a[0], a[1], a[2] if len(a) > 2 else os.path.join(HERE, "dist", "index.html"),
          a[3] if len(a) > 3 else None, a[4] if len(a) > 4 else None)
