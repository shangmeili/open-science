#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-run}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_EXECUTABLE="$ROOT_DIR/apps/desktop/src-tauri/target/debug/ai4s-workbench"
APP_WORKDIR="$ROOT_DIR/apps/desktop/src-tauri"
LOG_FILE="${TMPDIR:-/tmp}/ai4heor-dev-run.log"
BUNDLE_ID="com.ai4s.ai4heor"

dev_app_pids() {
  local cwd
  local pid
  while IFS= read -r pid; do
    [[ -n "$pid" ]] || continue
    cwd="$(lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -n 1)"
    [[ "$cwd" == "$APP_WORKDIR" ]] && echo "$pid"
  done < <(pgrep -f '^target/debug/ai4s-workbench([[:space:]]|$)' 2>/dev/null || true)
}

stop_dev_app() {
  local pid
  while IFS= read -r pid; do
    [[ -n "$pid" ]] || continue
    kill "$pid" 2>/dev/null || true
  done < <(dev_app_pids)

  for _ in {1..20}; do
    [[ -z "$(dev_app_pids)" ]] && return 0
    sleep 0.1
  done

  while IFS= read -r pid; do
    [[ -n "$pid" ]] || continue
    kill -KILL "$pid" 2>/dev/null || true
  done < <(dev_app_pids)
}

start_dev_app() {
  mkdir -p "$(dirname "$LOG_FILE")"
  : >"$LOG_FILE"
  (
    cd "$ROOT_DIR"
    nohup pnpm --filter @ai4s/desktop tauri dev --no-watch \
      </dev/null >>"$LOG_FILE" 2>&1 &
    echo $!
  )
}

wait_for_app() {
  local launcher_pid="$1"
  local pid
  for _ in {1..240}; do
    pid="$(dev_app_pids | head -n 1)"
    if [[ -n "$pid" ]]; then
      echo "$pid"
      return 0
    fi
    if ! kill -0 "$launcher_pid" 2>/dev/null; then
      echo "AI4HEOR development launch stopped before the app became ready." >&2
      tail -n 80 "$LOG_FILE" >&2 || true
      return 1
    fi
    sleep 0.5
  done

  echo "Timed out waiting for the AI4HEOR development app." >&2
  tail -n 80 "$LOG_FILE" >&2 || true
  return 1
}

stop_dev_app

case "$MODE" in
  --stop|stop)
    echo "AI4HEOR development app is stopped."
    ;;
  run)
    cd "$ROOT_DIR"
    exec pnpm --filter @ai4s/desktop tauri dev --no-watch
    ;;
  --verify|verify)
    launcher_pid="$(start_dev_app)"
    app_pid="$(wait_for_app "$launcher_pid")"
    echo "AI4HEOR development app is running (pid=$app_pid)."
    echo "Build log: $LOG_FILE"
    ;;
  --logs|logs)
    launcher_pid="$(start_dev_app)"
    wait_for_app "$launcher_pid" >/dev/null
    exec /usr/bin/log stream --info --style compact --predicate 'process == "ai4s-workbench"'
    ;;
  --telemetry|telemetry)
    launcher_pid="$(start_dev_app)"
    wait_for_app "$launcher_pid" >/dev/null
    exec /usr/bin/log stream --info --style compact --predicate "subsystem == \"$BUNDLE_ID\""
    ;;
  --debug|debug)
    cd "$ROOT_DIR"
    pnpm --filter @ai4s/desktop tauri build --debug --no-bundle
    exec lldb -- "$APP_EXECUTABLE"
    ;;
  *)
    echo "usage: $0 [run|--stop|--verify|--logs|--telemetry|--debug]" >&2
    exit 2
    ;;
esac
