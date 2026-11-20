# glyphbyte.dev

The static site for GlyphByte, assembled from the repository's own files so that one command
regenerates everything. Nothing on the site is hand-copied from elsewhere in the repo.

The look: airy and prismatic. Pale sky and soft light leaks by day, the same glass at night (it
follows the system dark mode). The hero and the byte builder show the glyphs as floating
dispersive glass rendered live with three.js; every other glyph on the site is SVG drawn from
`spec/glyphs.json` in the page's ink colour.

| URL | file in `site/dist/` | comes from |
|---|---|---|
| `/` | `index.html` | `site/src/landing.html` in `site/src/shell.html`; `style.css`, `site.js`, `spec/glyphs.json` and `napplet/src/nip19.js` inlined |
| `/app/` | `app/index.html` | `napplet/dist/index.html`, byte for byte: the reader (Read, Draw and Publish tabs; `#read`, `#draw`, `#publish` open a tab) |
| `/spec/` | `spec/index.html` | `spec/GLYPHBYTE.md` rendered to HTML inside the same shell, with a contents column |
| `/spec/test-vectors.json`, `/spec/glyphs.json`, `/spec/glyphs.svg`, `/spec/vectors/*` | `spec/...` | copied from `spec/` |
| `/sheet.svg` | `sheet.svg` | `spec/glyphs.svg`, the printable sheet |
| `/vendor/crystals.js` | `vendor/crystals.js` | `site/src/vendor/crystals.js`: the 3D crystals bundled with three.js (see below) |
| `/fonts/*` | `fonts/` | `site/src/fonts/`: Sora and JetBrains Mono, OFL (licences beside them) |
| `/favicon.svg` | `favicon.svg` | the mark (byte `0f`) built from `spec/glyphs.json` |
| `/404.html` | `404.html` | `site/src/404.html` |
| (server config) | `.htaccess` | `site/src/htaccess`, for Apache hosting |

Icons are Lucide (ISC, `site/src/icons-LICENSE.txt`), kept in `site/src/icons.json` and written
into templates as `{{icon:name}}`. The reader uses the same set. Nothing loads from another origin.

## Build

From the repository root, with any Python that has the `markdown` package (the only dependency):

```
python site/build.py
```

`site/dist/` is deleted and rebuilt every time. If `napplet/dist/index.html` does not exist the
script builds the napplet first (`cd napplet && python build.py weights.bin weights.bin.json`).
The build ends with a link check: every `href` and `src` in every generated page must resolve to
a file in `site/dist/`, and the script exits non-zero if one does not. `python site/build.py
--check` runs only that check.

## The 3D crystals

`site/three/crystals.js` is the source. Its bundle with three.js, `site/src/vendor/crystals.js`,
is committed, so neither the site build nor Vercel needs Node. After changing the source:

```
cd site/three && npm install && npm run build
```

It mounts on every `<canvas data-crystals>`: `data-crystals` alone follows the hero input
(`gb:bytes` events from `site.js`), `data-crystals="single"` follows the byte builder
(`gb:builder`). It renders a still frame when the visitor asks for reduced motion, stops when
off screen, drops pixels and then bloom on a slow device, and leaves an SVG fallback in place
where WebGL is missing. `--bg` in `style.css` must equal `PAGE` in `crystals.js`.

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

## Vercel

`vercel.json` at the repository root makes the site deploy from GitHub with no server: install
command `pip3 install -r site/requirements.txt`, build command `python3 site/build.py`, output
directory `site/dist`. Every push to `main` deploys production; every pull request gets a preview
URL. The DreamHost `deploy.sh` path still works for a manual upload of the same `site/dist/`.
