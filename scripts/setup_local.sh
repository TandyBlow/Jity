#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
ENV_NAME="${JITY_BACKEND_ENV:-jity-backend}"

has_command() {
  command -v "$1" >/dev/null 2>&1
}

echo "==> Preparing backend environment: $ENV_NAME"
if has_command conda; then
  if conda env list | awk '{print $1}' | grep -qx "$ENV_NAME"; then
    conda env update -n "$ENV_NAME" -f "$BACKEND_DIR/environment.yml" --prune
  else
    conda env create -f "$BACKEND_DIR/environment.yml"
  fi
else
  echo "ERROR: conda is required for the backend environment." >&2
  exit 1
fi

echo "==> Preparing backend .env"
if [[ ! -f "$BACKEND_DIR/.env" ]]; then
  cp "$BACKEND_DIR/.env.example" "$BACKEND_DIR/.env"
  echo "Created backend/.env. Set DEEPSEEK_API_KEY before LLM generation."
fi
mkdir -p "$BACKEND_DIR/data/campaigns" "$BACKEND_DIR/data/scripted_story" "$BACKEND_DIR/data/novels"

echo "==> Installing frontend dependencies"
if [[ -f "$FRONTEND_DIR/package-lock.json" ]]; then
  (cd "$FRONTEND_DIR" && npm ci)
else
  (cd "$FRONTEND_DIR" && npm install)
fi

echo "==> Preparing frontend .env.local"
if [[ ! -f "$FRONTEND_DIR/.env.local" ]]; then
  cp "$FRONTEND_DIR/.env.example" "$FRONTEND_DIR/.env.local"
  echo "Created frontend/.env.local."
fi

echo "==> Local environment is ready"
echo "Backend:  scripts/start_backend.sh"
echo "Frontend: scripts/start_frontend.sh"
echo "Both:     scripts/start_local.sh"
