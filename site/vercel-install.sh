#!/usr/bin/env bash
# Vercel install step. The build image's Python is uv-managed and rejects system-wide pip
# installs (PEP 668), so everything goes into a virtual environment in the working directory.
set -euo pipefail
REQ="$(dirname "$0")/requirements.txt"
if command -v uv >/dev/null 2>&1; then
  uv venv --quiet .venv
  uv pip install --quiet --python .venv/bin/python -r "$REQ"
elif python3 -m venv .venv 2>/dev/null && [ -x .venv/bin/pip ]; then
  .venv/bin/pip install --quiet -r "$REQ"
else
  pip3 install --break-system-packages -r "$REQ"
fi
echo "python: $([ -x .venv/bin/python ] && .venv/bin/python --version || python3 --version)"
