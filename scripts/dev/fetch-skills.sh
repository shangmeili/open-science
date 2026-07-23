#!/usr/bin/env bash
# Fetch Open Science's pinned MIT scientific Skill pack. Packaging remains
# fail-closed: every shipped entry must also have a hash-locked
# `validated-adapter` row in the release admission registry.
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
[ -f "$SRC/LICENSE" ] || { echo "No repository LICENSE in archive" >&2; exit 1; }
for skill_dir in "$OUT_DIR"/*; do
  [ -f "$skill_dir/SKILL.md" ] || continue
  cp "$SRC/LICENSE" "$skill_dir/LICENSE.txt"
done
echo "$AI4S_SKILLS_COMMIT" > "$OUT_DIR/.commit"
rm -rf "$TMP"

echo "Placed ai4s-skills@${AI4S_SKILLS_COMMIT:0:7} in $OUT_DIR:"
ls "$OUT_DIR"
