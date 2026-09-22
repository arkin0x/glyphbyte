"""Export synthetic scenes for the JavaScript harnesses: PGM images plus truth in ORIGINAL
image coordinates, and the Python detector's reading for comparison.
usage: PYTHONPATH=. python napplet/test/export_scenes.py <out_dir> [n] [seed]"""
import json, os, sys
import cv2, numpy as np
from glyphbyte.synth import make_scene, load_backdrops
from glyphbyte.detect import detect

out, n, seed = sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 40, int(sys.argv[3]) if len(sys.argv) > 3 else 77
os.makedirs(out, exist_ok=True)
bd = load_backdrops('bench/backdrops'); rng = np.random.default_rng(seed); items = []
for i in range(n):
    sc = make_scene(rng, bd)
    gray = cv2.cvtColor(sc.image, cv2.COLOR_BGR2GRAY)
    with open(f'{out}/scene_{i:02d}.pgm', 'wb') as f:
        f.write(f'P5\n{gray.shape[1]} {gray.shape[0]}\n255\n'.encode()); f.write(gray.tobytes())
    det = detect(sc.image); s = det.scale
    items.append({'i': i, 'hex': sc.data.hex(),
                  'truth': [{'byte': c['byte'], 'center': c['corners'].mean(axis=0).tolist(),
                             'size': float(np.linalg.norm(c['corners'][0] - c['corners'][2]) / 1.414)} for c in sc.cells],
                  'py': {'frames': [{'center': (f.center / s).tolist(), 'kind': int(f.kind), 'size': float(f.size / s)} for f in det.frames],
                         'baseline': None if det.baseline is None else (det.baseline / s).tolist(), 'start_known': bool(det.start_known),
                         'direction': det.direction.tolist(), 'up': det.up.tolist(), 'light_ink': bool(det.light_ink)}})
json.dump(items, open(f'{out}/scenes.json', 'w'))
print('exported', n, 'scenes to', out)
