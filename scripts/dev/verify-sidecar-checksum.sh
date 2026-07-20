#!/usr/bin/env bash
# Cross-platform compatibility wrapper for the Python verifier.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
if command -v python3 >/dev/null 2>&1; then
  exec python3 "$ROOT/scripts/dev/verify_sidecar_checksum.py" "$@"
fi
exec python "$ROOT/scripts/dev/verify_sidecar_checksum.py" "$@"
