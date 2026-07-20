#!/usr/bin/env bash
# Verify one downloaded sidecar release archive before extraction.
set -euo pipefail

if [ "$#" -lt 4 ] || [ "$#" -gt 5 ]; then
  echo "usage: $0 FILE PRODUCT VERSION ASSET [CHECKSUM_FILE]" >&2
  exit 2
fi

FILE="$1"
PRODUCT="$2"
VERSION="$3"
ASSET="$4"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CHECKSUM_FILE="${5:-$ROOT/scripts/dev/sidecar-checksums.sha256}"
KEY="$PRODUCT/$VERSION/$ASSET"

EXPECTED="$(awk -v key="$KEY" '$2 == key { print $1 }' "$CHECKSUM_FILE")"
if ! [[ "$EXPECTED" =~ ^[0-9a-f]{64}$ ]]; then
  echo "No unique pinned SHA-256 for $KEY" >&2
  exit 1
fi

if command -v sha256sum >/dev/null 2>&1; then
  ACTUAL="$(sha256sum "$FILE" | awk '{ print $1 }')"
elif command -v shasum >/dev/null 2>&1; then
  ACTUAL="$(shasum -a 256 "$FILE" | awk '{ print $1 }')"
elif command -v openssl >/dev/null 2>&1; then
  ACTUAL="$(openssl dgst -sha256 "$FILE" | awk '{ print $NF }')"
else
  echo "No SHA-256 implementation is available" >&2
  exit 1
fi

if [ "$ACTUAL" != "$EXPECTED" ]; then
  echo "SHA-256 mismatch for $KEY: expected $EXPECTED, got $ACTUAL" >&2
  exit 1
fi
echo "Verified SHA-256 for $KEY"
