#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT_DIR/.local/logs"
mkdir -p "$LOG_DIR"

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
trap cleanup EXIT INT TERM

echo "==> Starting backend on http://localhost:${JITY_BACKEND_PORT:-8000}"
"$ROOT_DIR/scripts/start_backend.sh" >"$BACKEND_LOG" 2>&1 &
backend_pid="$!"

echo "==> Starting frontend on http://localhost:${JITY_FRONTEND_PORT:-3000}"
"$ROOT_DIR/scripts/start_frontend.sh" >"$FRONTEND_LOG" 2>&1 &
frontend_pid="$!"

echo "Backend log:  $BACKEND_LOG"
echo "Frontend log: $FRONTEND_LOG"
echo "Press Ctrl+C to stop both processes."

while true; do
  if ! kill -0 "$backend_pid" >/dev/null 2>&1; then
    echo "Backend process exited; stopping frontend."
    break
  fi
  if ! kill -0 "$frontend_pid" >/dev/null 2>&1; then
    echo "Frontend process exited; stopping backend."
    break
  fi
  sleep 1
done
