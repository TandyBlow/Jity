#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT_DIR/.local/logs"
BACKEND_PORT="${JITY_BACKEND_PORT:-8000}"
FRONTEND_PORT="${JITY_FRONTEND_PORT:-3000}"

if ! command -v lsof >/dev/null 2>&1; then
  echo "ERROR: lsof is required to check listening ports." >&2
  exit 1
fi

port_in_use() {
  lsof -nP -iTCP:"$1" -sTCP:LISTEN -t >/dev/null 2>&1
}

BACKEND_LOG="$LOG_DIR/backend.log"
FRONTEND_LOG="$LOG_DIR/frontend.log"

backend_pid=""
frontend_pid=""

cleanup() {
  if [[ -n "$frontend_pid" ]] && kill -0 "$frontend_pid" >/dev/null 2>&1; then
    kill "$frontend_pid" >/dev/null 2>&1 || true
  fi
  if [[ -n "$backend_pid" ]] && kill -0 "$backend_pid" >/dev/null 2>&1; then
    kill "$backend_pid" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if port_in_use "$BACKEND_PORT"; then
  echo "==> Port $BACKEND_PORT already has a listener; skipping backend startup (service identity not verified)."
else
  mkdir -p "$LOG_DIR"
  echo "==> Starting backend on http://localhost:$BACKEND_PORT"
  "$ROOT_DIR/scripts/start_backend.sh" >"$BACKEND_LOG" 2>&1 &
  backend_pid="$!"
  echo "Backend log:  $BACKEND_LOG"
fi

if port_in_use "$FRONTEND_PORT"; then
  echo "==> Port $FRONTEND_PORT already has a listener; skipping frontend startup (service identity not verified)."
else
  mkdir -p "$LOG_DIR"
  echo "==> Starting frontend on http://localhost:$FRONTEND_PORT"
  "$ROOT_DIR/scripts/start_frontend.sh" >"$FRONTEND_LOG" 2>&1 &
  frontend_pid="$!"
  echo "Frontend log: $FRONTEND_LOG"
fi

if [[ -z "$backend_pid" && -z "$frontend_pid" ]]; then
  echo "Both ports are occupied; nothing started. Existing processes were left untouched."
  exit 0
fi

echo "Press Ctrl+C to stop only the processes started by this script."

while true; do
  if [[ -n "$backend_pid" ]] && ! kill -0 "$backend_pid" >/dev/null 2>&1; then
    echo "Backend process exited; cleaning up processes started by this script. See $BACKEND_LOG"
    exit 1
  fi
  if [[ -n "$frontend_pid" ]] && ! kill -0 "$frontend_pid" >/dev/null 2>&1; then
    echo "Frontend process exited; cleaning up processes started by this script. See $FRONTEND_LOG"
    exit 1
  fi
  sleep 1
done
