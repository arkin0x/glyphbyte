#!/usr/bin/env bash
# Vercel build step: use the environment vercel-install.sh created, if it exists.
set -euo pipefail
PY=python3
[ -x .venv/bin/python ] && PY=.venv/bin/python
exec "$PY" "$(dirname "$0")/build.py"
