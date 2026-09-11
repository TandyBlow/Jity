#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
ENV_NAME="${JITY_BACKEND_ENV:-jity-backend}"
HOST="${JITY_BACKEND_HOST:-0.0.0.0}"
PORT="${JITY_BACKEND_PORT:-8000}"

if [[ ! -f "$BACKEND_DIR/.env" && -f "$BACKEND_DIR/.env.example" ]]; then
  cp "$BACKEND_DIR/.env.example" "$BACKEND_DIR/.env"
  echo "Created backend/.env. Set DEEPSEEK_API_KEY before LLM generation."
fi

mkdir -p "$BACKEND_DIR/data/campaigns" "$BACKEND_DIR/data/scripted_story" "$BACKEND_DIR/data/novels"

cd "$BACKEND_DIR"
if command -v conda >/dev/null 2>&1 && conda env list | awk '{print $1}' | grep -qx "$ENV_NAME"; then
  exec conda run --no-capture-output -n "$ENV_NAME" uvicorn app.main:app --reload --host "$HOST" --port "$PORT"
fi

echo "WARNING: conda env '$ENV_NAME' not found; falling back to current Python." >&2
exec uvicorn app.main:app --reload --host "$HOST" --port "$PORT"
