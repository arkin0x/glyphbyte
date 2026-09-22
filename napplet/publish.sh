#!/bin/sh
# Publish the napplet: upload dist/index.html to a Blossom server and publish the
# kind 35129 manifest (NIP-5D) with nak. Nothing here runs without your key.
#
#   BLOSSOM=https://blossom.example.com RELAYS="wss://relay.damus.io wss://nos.lol" \
#   NAK_KEY="--sec nsec1..."   # or --connect bunker://... ; see `nak event --help`
#   ./publish.sh [dist/index.html]
set -eu
FILE=${1:-"$(dirname "$0")/dist/index.html"}
: "${BLOSSOM:?set BLOSSOM to a Blossom server url}"
: "${RELAYS:?set RELAYS to space-separated relay urls}"
NAK_KEY=${NAK_KEY:-}
HASH=$(sha256sum "$FILE" | cut -d' ' -f1)
AGG=$(printf '%s /index.html\n' "$HASH" | sha256sum | cut -d' ' -f1)
echo "index.html sha256  $HASH"
echo "aggregate (NIP-5A) $AGG"
# shellcheck disable=SC2086
nak blossom upload --server "$BLOSSOM" $NAK_KEY "$FILE"
# shellcheck disable=SC2086
nak event -k 35129 -d glyphbyte \
  -t "path=/index.html;$HASH" \
  -t "x=$AGG;aggregate" \
  -t "server=$BLOSSOM" \
  -t "title=glyphbyte" \
  -t "description=Hand-drawn symbols to bytes, on device: draw a nostr event id prefix on anything, photograph it, get the bytes." \
  -t "source=https://embassy.local:52248/arkin0x/glyphbyte" \
  $NAK_KEY $RELAYS
