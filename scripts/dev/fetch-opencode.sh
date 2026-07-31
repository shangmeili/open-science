#!/usr/bin/env bash
# Build the pinned, reviewed OpenCode derivative and place it as a Tauri sidecar
# (apps/desktop/src-tauri/binaries/opencode-<target-triple>).
# Runs per-platform locally and in CI so the binary never lives in git.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TRIPLE="${1:-$(rustc -Vv | sed -n 's/host: //p')}"
exec bash "$ROOT/scripts/dev/build-opencode.sh" "$TRIPLE"
