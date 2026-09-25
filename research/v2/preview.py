"""Contact sheet: each set (rows) x each medium (column groups), a few random bytes."""
import sys, numpy as np, cv2
sys.path.insert(0, '.')
from draw import photo_of_glyph, MEDIA
from sets import SETS
import os
ONLY = os.environ.get("SETS")
sys.path.insert(0, '../..')
from glyphbyte.synth import load_backdrops
bd = load_backdrops('../../bench/backdrops')
rng = np.random.default_rng(int(sys.argv[1]) if len(sys.argv) > 1 else 0)
T = 150
rows = []
for s in (ONLY.split(",") if ONLY else SETS):
    tiles = []
    for m in MEDIA:
        for k in range(3):
            g, q, light, cell = photo_of_glyph(s, int(rng.integers(0, 4096 if s == "sun" else 256)), m, rng, bd)
            H = cv2.getPerspectiveTransform(q.astype(np.float32), np.float32([[25,25],[125,25],[125,125],[25,125]]))
            tiles.append(cv2.warpPerspective(g, H, (T, T)))
        tiles.append(np.full((T, 10), 255, np.uint8))
    rows.append(np.hstack(tiles))
cv2.imwrite('out/preview.png', np.vstack(rows))
print('ok')
