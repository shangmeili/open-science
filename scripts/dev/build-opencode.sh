#!/usr/bin/env bash
# Reproducibly build AI4HEOR's reviewed OpenCode derivative from pinned source.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
MANIFEST="$ROOT/runtime/opencode-patch/manifest.json"
PATCH="$ROOT/runtime/opencode-patch/ai4heor-system-context.patch"
OUT_DIR="$ROOT/apps/desktop/src-tauri/binaries"
TRIPLE="${1:-$(rustc -Vv | sed -n 's/host: //p')}"

UPSTREAM_COMMIT="10c894bdeef3618f5666fb506ef7f9491bb964d8"
SOURCE_URL="https://github.com/anomalyco/opencode/archive/${UPSTREAM_COMMIT}.tar.gz"
sourceArchiveSha256="774e4a5bf89d7e8191accfe5e3aa55de67339ddb3914e7c990f5fccff5719cac"
patchSha256="dffadfb1f43cda1594046ee04bd1f7013de0abe4f527bc01fbc45ee8dc5e5568"
PATCHED_VERSION="1.17.13-ai4heor.2"
BUN_VERSION="1.3.14"

case "$TRIPLE" in
  aarch64-apple-darwin)       DIST="opencode-darwin-arm64"; DEST="opencode-$TRIPLE" ;;
  x86_64-apple-darwin)        DIST="opencode-darwin-x64"; DEST="opencode-$TRIPLE" ;;
  x86_64-pc-windows-msvc)     DIST="opencode-windows-x64"; DEST="opencode-$TRIPLE.exe" ;;
  aarch64-pc-windows-msvc)    DIST="opencode-windows-arm64"; DEST="opencode-$TRIPLE.exe" ;;
  x86_64-unknown-linux-gnu)   DIST="opencode-linux-x64"; DEST="opencode-$TRIPLE" ;;
  aarch64-unknown-linux-gnu)  DIST="opencode-linux-arm64"; DEST="opencode-$TRIPLE" ;;
  *) echo "Unsupported triple: $TRIPLE" >&2; exit 1 ;;
esac

command -v bun >/dev/null 2>&1 || {
  echo "Bun $BUN_VERSION is required to build the reviewed OpenCode sidecar." >&2
  exit 1
}
test "$(bun --version)" = "$BUN_VERSION" || {
  echo "Expected Bun $BUN_VERSION; found $(bun --version)." >&2
  exit 1
}

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
ARCHIVE="$TMP/opencode-source.tar.gz"
curl -fsSL "$SOURCE_URL" -o "$ARCHIVE"
PYTHON="$(command -v python3 || command -v python || true)"
test -n "$PYTHON" || {
  echo "Python is required to verify the reviewed OpenCode source and patch." >&2
  exit 1
}
verify_sha256() {
  "$PYTHON" - "$1" "$2" <<'PY'
import hashlib
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
expected = sys.argv[2]
actual = hashlib.sha256(path.read_bytes()).hexdigest()
if actual != expected:
    raise SystemExit(
        f"SHA-256 mismatch for {path}: expected {expected}, found {actual}"
    )
print(f"{path}: OK")
PY
}
verify_sha256 "$ARCHIVE" "$sourceArchiveSha256"
verify_sha256 "$PATCH" "$patchSha256"

tar -xzf "$ARCHIVE" -C "$TMP"
SOURCE="$TMP/opencode-$UPSTREAM_COMMIT"
test -d "$SOURCE"
git -C "$SOURCE" apply --check --unidiff-zero "$PATCH"
git -C "$SOURCE" apply --unidiff-zero "$PATCH"

(
  cd "$SOURCE"
  # tree-sitter-powershell's install script otherwise resolves node-gyp@latest
  # outside the reviewed lockfile. Use the content-addressed node-gyp already
  # pinned by the upstream bun.lock on every supported build host.
  export npm_config_node_gyp="$SOURCE/node_modules/node-gyp/bin/node-gyp.js"
  bun install --frozen-lockfile
  bun test --cwd packages/opencode \
    test/session/system-context.test.ts \
    test/session/processor-effect.test.ts \
    test/permission/next.test.ts \
    test/project/project-directory.test.ts
  bun run --cwd packages/opencode typecheck
  OPENCODE_VERSION=1.17.13-ai4heor.2 bun run --cwd packages/opencode build --single
)

BIN="$SOURCE/packages/opencode/dist/$DIST/bin/opencode"
if [[ "$TRIPLE" == *windows* ]]; then
  BIN="$BIN.exe"
fi
test -f "$BIN"
VERSION="$($BIN --version | tr -d '\r\n')"
test "$VERSION" = "$PATCHED_VERSION" || {
  echo "Patched OpenCode reported unexpected version: $VERSION" >&2
  exit 1
}
mkdir -p "$OUT_DIR"
cp "$BIN" "$OUT_DIR/$DEST"
if [[ "$TRIPLE" != *windows* ]]; then chmod +x "$OUT_DIR/$DEST"; fi
echo "Placed reviewed OpenCode $PATCHED_VERSION sidecar for $TRIPLE in $OUT_DIR"
