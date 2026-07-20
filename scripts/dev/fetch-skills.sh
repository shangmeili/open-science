#!/usr/bin/env bash
# Fetch a pinned external skill pack into a git-ignored review cache.
# This does NOT make the skills deployable or add them to an installer. A
# third-party asset is bundled only after its own hash-locked registry entry
# reaches `validated-adapter` and the runtime admission tests pass.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

# ---- ai4s-skills: pinned review candidate pack ----
AI4S_SKILLS_COMMIT="${AI4S_SKILLS_COMMIT:-8fa2ab0523082c135598909b227ed8feb48263ad}"
OUT_DIR="$ROOT/runtime/skills/external/ai4s-skills"

URL="https://github.com/ai4s-research/ai4s-skills/archive/${AI4S_SKILLS_COMMIT}.tar.gz"
TMP="$(mktemp -d)"
echo "Downloading $URL"
curl -fsSL "$URL" -o "$TMP/skills.tar.gz"
tar -xzf "$TMP/skills.tar.gz" -C "$TMP"

SRC="$(find "$TMP" -maxdepth 1 -type d -name 'ai4s-skills-*' | head -1)"
[ -d "$SRC/skills" ] || { echo "No skills/ directory in archive" >&2; exit 1; }

rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR"
cp -R "$SRC/skills/." "$OUT_DIR/"
echo "$AI4S_SKILLS_COMMIT" > "$OUT_DIR/.commit"
rm -rf "$TMP"

echo "Placed ai4s-skills@${AI4S_SKILLS_COMMIT:0:7} in $OUT_DIR:"
ls "$OUT_DIR"
