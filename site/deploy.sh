#!/usr/bin/env bash
# Upload site/dist/ to DreamHost with rsync over SSH.
#
#   DEPLOY_TARGET='user@server.dreamhost.com:~/glyphbyte.dev/' ./site/deploy.sh [--dry-run]
#   DEPLOY_SSH_OPTS='-p 22 -i ~/.ssh/dreamhost'     optional, passed to ssh
#
# --delete removes anything under the target that is not in dist/ (the .well-known directory is
# left alone, DreamHost keeps certificate challenges there). Files land as 0644 and directories as
# 0755 so Apache can read them whatever the local modes are. No credentials live in this script.
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
DIST="$HERE/dist"

if [ -z "${DEPLOY_TARGET:-}" ]; then
  echo "DEPLOY_TARGET is not set. Example:" >&2
  echo "  DEPLOY_TARGET='user@server.dreamhost.com:~/glyphbyte.dev/' $0 --dry-run" >&2
  exit 2
fi
if [ ! -f "$DIST/index.html" ] || [ ! -f "$DIST/.htaccess" ] || [ ! -f "$DIST/app/index.html" ]; then
  echo "$DIST is not a complete build; run: python site/build.py" >&2
  exit 2
fi

DRY=()
for arg in "$@"; do
  case "$arg" in
    --dry-run|-n) DRY=(--dry-run) ;;
    *) echo "unknown argument: $arg (only --dry-run is accepted)" >&2; exit 2 ;;
  esac
done

CMD=(rsync -avz --delete --chmod=D755,F644 --exclude=.well-known ${DRY[@]+"${DRY[@]}"}
     -e "ssh ${DEPLOY_SSH_OPTS:-}" "$DIST/" "$DEPLOY_TARGET")

if [ "${#DRY[@]}" -gt 0 ]; then
  echo "dry run: nothing will be uploaded or deleted"
fi
echo "uploading $DIST/ to $DEPLOY_TARGET (deleting remote files that are not in dist/)"
printf '+'; printf ' %q' "${CMD[@]}"; printf '\n'
exec "${CMD[@]}"
