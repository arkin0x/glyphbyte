# glyphbyte.dev

The static site for GlyphByte, assembled from the repository's own files so that one command
regenerates everything. Nothing on the site is hand-copied from elsewhere in the repo.

| URL | file in `site/dist/` | comes from |
|---|---|---|
| `/` | `index.html` | `site/src/landing.html` in `site/src/shell.html`, CSS from `site/src/style.css` inlined |
| `/app/` | `app/index.html` | `napplet/dist/index.html`, byte for byte: the reader and encoder, camera via file input, relay over WebSocket |
| `/spec/` | `spec/index.html` | `spec/GLYPHBYTE.md` rendered to HTML inside the same shell |
| `/spec/test-vectors.json`, `/spec/glyphs.json`, `/spec/glyphs.svg`, `/spec/vectors/*` | `spec/...` | copied from `spec/` |
| `/sheet.svg` | `sheet.svg` | `spec/glyphs.svg`, the printable sheet |
| `/img/row-e8ed3798c6ff.png`, `/img/photo-01.jpg` | `img/` | the reference row as is; the photo resized with OpenCV to 1200 px on the long side, JPEG quality 85 |
| `/favicon.svg` | `favicon.svg` | the house polygon from `spec/glyphs.json` |
| `/404.html` | `404.html` | `site/src/404.html`; Apache serves it through `ErrorDocument` |
| (server config) | `.htaccess` | `site/src/htaccess`: `DirectoryIndex`, `ErrorDocument 404`, `AddType` for svg, json and wasm |

The pages use no external scripts, fonts or stylesheets. The landing and spec pages follow the
system dark mode and keep a 16 px gutter on phones; tables scroll inside their container.

## Build

From the repository root, with the project's Python (numpy, opencv and the `markdown` package;
install the last one with `uv pip install --python .venv/bin/python markdown` if it is missing):

```
python site/build.py
```

`site/dist/` is deleted and rebuilt every time. If `napplet/dist/index.html` does not exist the
script builds the napplet first (`cd napplet && python build.py weights.bin weights.bin.json`).
The build ends with a link check: every `href` and `src` in every generated page must resolve to
a file in `site/dist/`, and the script exits non-zero if one does not. `python site/build.py
--check` runs only that check.

## Preview

```
cd site/dist && python -m http.server 8000
```

then open http://localhost:8000/ . The reader at `/app/` works in the preview too, including the
relay lookup; only the `.htaccess` rules (404 page, directory index) need Apache. Directory URLs
such as `/app/` resolve to `index.html` in both.

## Deploy

DreamHost shared hosting serves the domain from a directory named after it in the shell user's
home. The upload is rsync over SSH; the target comes from the environment and nothing is stored
in the repository:

```
export DEPLOY_TARGET='user@server.dreamhost.com:~/glyphbyte.dev/'
export DEPLOY_SSH_OPTS='-i ~/.ssh/dreamhost'      # optional
./site/deploy.sh --dry-run                        # lists what would change, uploads nothing
./site/deploy.sh
```

The script refuses to run without `DEPLOY_TARGET` or without a complete build, runs
`rsync -avz --delete --chmod=D755,F644`, and leaves `.well-known/` on the server alone. Everything
else under the target that is not in `site/dist/` is deleted, so point it at the site's own
directory, never at the home directory.
