#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REMOVE_DEPS=0
REMOVE_RUNTIME=0

usage() {
  cat <<'EOF'
Usage: scripts/clean_local.sh [--deps] [--runtime]

Default:
  Remove Python caches, pytest caches, Next.js build output, TypeScript build info,
  local logs, and common temp files.

Options:
  --deps     Also remove frontend/node_modules.
  --runtime  Also remove local SQLite/runtime generated files under backend/data
             and playtest_logs. This deletes local game state.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --deps)
      REMOVE_DEPS=1
      shift
      ;;
    --runtime)
      REMOVE_RUNTIME=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

echo "==> Removing caches and build outputs"
find "$ROOT_DIR" \
  -path "$ROOT_DIR/frontend/node_modules" -prune -o \
  -type d \( -name "__pycache__" -o -name ".pytest_cache" -o -name ".mypy_cache" -o -name ".ruff_cache" \) \
  -print -exec rm -rf {} +

rm -rf \
  "$ROOT_DIR/frontend/.next" \
  "$ROOT_DIR/frontend/out" \
  "$ROOT_DIR/frontend/tsconfig.tsbuildinfo" \
  "$ROOT_DIR/.local/logs"

find "$ROOT_DIR" \
  -path "$ROOT_DIR/frontend/node_modules" -prune -o \
  -type f \( -name "*.pyc" -o -name "*.pyo" -o -name ".coverage" \) \
  -print -delete

if [[ "$REMOVE_DEPS" -eq 1 ]]; then
  echo "==> Removing frontend dependencies"
  rm -rf "$ROOT_DIR/frontend/node_modules"
fi

if [[ "$REMOVE_RUNTIME" -eq 1 ]]; then
  echo "==> Removing runtime data"
  rm -rf "$ROOT_DIR/playtest_logs"
  find "$ROOT_DIR/backend/data" -type f \
    \( -name "*.sqlite3" -o -name "*.sqlite3-*" -o -name "*.db" -o -name "*.db-*" \) \
    -print -delete 2>/dev/null || true
fi

echo "==> Clean complete"
