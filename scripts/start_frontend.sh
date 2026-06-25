#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"
PORT="${JITY_FRONTEND_PORT:-3000}"

if [[ ! -f "$FRONTEND_DIR/.env.local" && -f "$FRONTEND_DIR/.env.example" ]]; then
  cp "$FRONTEND_DIR/.env.example" "$FRONTEND_DIR/.env.local"
  echo "Created frontend/.env.local."
fi

if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
  echo "node_modules not found; installing frontend dependencies."
  if [[ -f "$FRONTEND_DIR/package-lock.json" ]]; then
    (cd "$FRONTEND_DIR" && npm ci)
  else
    (cd "$FRONTEND_DIR" && npm install)
  fi
fi

cd "$FRONTEND_DIR"
exec npm run dev -- --port "$PORT"
