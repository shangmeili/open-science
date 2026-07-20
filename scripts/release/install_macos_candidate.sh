#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "usage: $0 --dmg <path> --sha256 <digest> [--launch]" >&2
  exit 2
}

DMG=""
EXPECTED_SHA256=""
LAUNCH=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dmg)
      [[ $# -ge 2 ]] || usage
      DMG="$2"
      shift 2
      ;;
    --sha256)
      [[ $# -ge 2 ]] || usage
      EXPECTED_SHA256="$2"
      shift 2
      ;;
    --launch)
      LAUNCH=true
      shift
      ;;
    *)
      usage
      ;;
  esac
done

[[ "$(uname -s)" == "Darwin" ]] || {
  echo "This installer is only for macOS." >&2
  exit 1
}
[[ -n "$DMG" && -n "$EXPECTED_SHA256" ]] || usage
[[ -f "$DMG" ]] || {
  echo "DMG not found: $DMG" >&2
  exit 1
}
[[ "$EXPECTED_SHA256" =~ ^[0-9a-fA-F]{64}$ ]] || {
  echo "Expected SHA-256 must contain exactly 64 hexadecimal characters." >&2
  exit 1
}

DMG="$(cd "$(dirname "$DMG")" && pwd)/$(basename "$DMG")"
ACTUAL_SHA256="$(shasum -a 256 "$DMG" | awk '{print $1}')"
NORMALIZED_EXPECTED_SHA256="$(printf '%s' "$EXPECTED_SHA256" | tr '[:upper:]' '[:lower:]')"
[[ "$ACTUAL_SHA256" == "$NORMALIZED_EXPECTED_SHA256" ]] || {
  echo "DMG SHA-256 does not match the expected digest." >&2
  exit 1
}

DESTINATION="/Applications/AI4HEOR.app"
if pgrep -f "^${DESTINATION}/Contents/MacOS/ai4s-workbench([[:space:]]|$)" >/dev/null 2>&1; then
  echo "Quit the installed AI4HEOR app before replacing it." >&2
  exit 1
fi

MOUNT_POINT=""
STAGED_APP="/Applications/.AI4HEOR.install.$$.app"
BACKUP_APP=""
INSTALLED=false

cleanup() {
  rm -rf "$STAGED_APP"
  if [[ -n "$MOUNT_POINT" && -d "$MOUNT_POINT" ]]; then
    hdiutil detach "$MOUNT_POINT" -quiet >/dev/null 2>&1 || true
  fi
}

rollback() {
  local status=$?
  trap - EXIT
  if [[ "$status" -ne 0 && "$INSTALLED" == true ]]; then
    pkill -f "^${DESTINATION}/Contents/MacOS/(ai4s-workbench|opencode)([[:space:]]|$)" >/dev/null 2>&1 || true
    rm -rf "$DESTINATION"
    if [[ -n "$BACKUP_APP" && -d "$BACKUP_APP" ]]; then
      mv "$BACKUP_APP" "$DESTINATION"
      echo "Installation failed; the previous AI4HEOR app was restored." >&2
    fi
  fi
  cleanup
  exit "$status"
}
trap rollback EXIT

while IFS=$'\t' read -r _device _type candidate_mount; do
  if [[ "$candidate_mount" == /Volumes/* ]]; then
    MOUNT_POINT="$candidate_mount"
    break
  fi
done < <(hdiutil attach -readonly -nobrowse "$DMG")

[[ -n "$MOUNT_POINT" ]] || {
  echo "The DMG mounted without an application volume." >&2
  exit 1
}
SOURCE_APP="$MOUNT_POINT/AI4HEOR.app"
[[ -d "$SOURCE_APP" ]] || {
  echo "AI4HEOR.app is missing from the mounted DMG." >&2
  exit 1
}

SOURCE_VERSION="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$SOURCE_APP/Contents/Info.plist")"
SOURCE_ARCHITECTURES="$(lipo -archs "$SOURCE_APP/Contents/MacOS/ai4s-workbench")"
[[ "$SOURCE_ARCHITECTURES" == "x86_64" ]] || {
  echo "Expected a thin x86_64 app, found: $SOURCE_ARCHITECTURES" >&2
  exit 1
}

ditto "$SOURCE_APP" "$STAGED_APP"
xattr -cr "$STAGED_APP"

if [[ -d "$DESTINATION" ]]; then
  PREVIOUS_VERSION="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$DESTINATION/Contents/Info.plist" 2>/dev/null || echo unknown)"
  BACKUP_ROOT="$HOME/Library/Application Support/AI4HEOR/install-backups"
  mkdir -p "$BACKUP_ROOT"
  BACKUP_APP="$BACKUP_ROOT/AI4HEOR-${PREVIOUS_VERSION}-$(date -u +%Y%m%dT%H%M%SZ).app"
  mv "$DESTINATION" "$BACKUP_APP"
fi

mv "$STAGED_APP" "$DESTINATION"
INSTALLED=true

INSTALLED_VERSION="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$DESTINATION/Contents/Info.plist")"
[[ "$INSTALLED_VERSION" == "$SOURCE_VERSION" ]] || {
  echo "Installed version does not match the mounted candidate." >&2
  exit 1
}

if [[ "$LAUNCH" == true ]]; then
  /usr/bin/open -n "$DESTINATION"
  MAIN_PID=""
  OPENCODE_PID=""
  for _ in {1..120}; do
    MAIN_PID="$(pgrep -f "^${DESTINATION}/Contents/MacOS/ai4s-workbench([[:space:]]|$)" | head -n 1 || true)"
    OPENCODE_PID="$(pgrep -f "^${DESTINATION}/Contents/MacOS/opencode([[:space:]]|$)" | head -n 1 || true)"
    [[ -n "$MAIN_PID" && -n "$OPENCODE_PID" ]] && break
    sleep 0.5
  done
  [[ -n "$MAIN_PID" && -n "$OPENCODE_PID" ]] || {
    echo "The installed app did not reach main-process and OpenCode readiness." >&2
    exit 1
  }
fi

trap - EXIT
cleanup
echo "Installed AI4HEOR $INSTALLED_VERSION from $(basename "$DMG")."
echo "Verified SHA-256: $ACTUAL_SHA256"
if [[ -n "$BACKUP_APP" ]]; then
  echo "Previous app backup: $BACKUP_APP"
fi
if [[ "$LAUNCH" == true ]]; then
  echo "Launch readiness: main process and bundled OpenCode are running."
fi
