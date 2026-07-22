#!/usr/bin/env bash
# Fetch the pinned agent-browser binary and place it as a Tauri sidecar
# (apps/desktop/src-tauri/binaries/agent-browser-<target-triple>).
# Runs per-platform locally and in CI so the binary never lives in git.
# agent-browser ships raw (unarchived) binaries per platform on its releases.
set -euo pipefail

AGENT_BROWSER_VERSION="${AGENT_BROWSER_VERSION:-0.32.1}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT_DIR="$ROOT/apps/desktop/src-tauri/binaries"
LICENSE_DIR="$ROOT/runtime/agent-browser"
mkdir -p "$OUT_DIR"
mkdir -p "$LICENSE_DIR"

# Resolve the Rust target triple (arg 1 overrides; else host).
TRIPLE="${1:-$(rustc -Vv | sed -n 's/host: //p')}"

case "$TRIPLE" in
  aarch64-apple-darwin)         ASSET="agent-browser-darwin-arm64"; EXPECTED_SHA256="13d54d6ac027abcafde7e6bfa16c4e266315e80e7fafd96dc6ba455377a56162" ;;
  x86_64-apple-darwin)          ASSET="agent-browser-darwin-x64"; EXPECTED_SHA256="898851be00042231369234b84dbdce1383d3262a2c5fe43c0ff55193f8151d94" ;;
  x86_64-pc-windows-msvc)       ASSET="agent-browser-win32-x64.exe"; EXPECTED_SHA256="ff419b70fdea810d9f991020694dd436ae5f35f7807ed2e5e743daa0f3e13a2b" ;;
  x86_64-unknown-linux-gnu)     ASSET="agent-browser-linux-x64"; EXPECTED_SHA256="a72c905c384df9de839f33e53b28c9369eb9bb7af0ee20beb042a8243446df3d" ;;
  aarch64-unknown-linux-gnu)    ASSET="agent-browser-linux-arm64"; EXPECTED_SHA256="59704e87ec2ca35b4b2cf83964693a2dc92e50b458c0328c591706a8231b2268" ;;
  *) echo "Unsupported triple for agent-browser: $TRIPLE" >&2; exit 1 ;;
esac

URL="https://github.com/vercel-labs/agent-browser/releases/download/v${AGENT_BROWSER_VERSION}/${ASSET}"
case "$TRIPLE" in
  *windows*) DEST="$OUT_DIR/agent-browser-$TRIPLE.exe" ;;
  *)         DEST="$OUT_DIR/agent-browser-$TRIPLE" ;;
esac

echo "Downloading $URL"
curl -fsSL "$URL" -o "$DEST"
PYTHON_BIN="${PYTHON:-$(command -v python3 || command -v python)}"
ACTUAL_SHA256="$($PYTHON_BIN -c 'import hashlib, pathlib, sys; print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())' "$DEST")"
if [[ "$ACTUAL_SHA256" != "$EXPECTED_SHA256" ]]; then
  echo "Checksum mismatch for $ASSET" >&2
  exit 1
fi
curl -fsSL "https://raw.githubusercontent.com/vercel-labs/agent-browser/v${AGENT_BROWSER_VERSION}/LICENSE" \
  -o "$LICENSE_DIR/LICENSE.txt"
printf '%s\n' "$AGENT_BROWSER_VERSION" > "$LICENSE_DIR/VERSION"
chmod +x "$DEST"
echo "Placed sidecar for $TRIPLE at $DEST"
