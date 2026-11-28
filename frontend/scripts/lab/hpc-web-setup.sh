#!/bin/bash
set -euo pipefail
export PATH=$HOME/node20/node-v20.18.1-linux-x64/bin:$PATH
mkdir -p $HOME/jity-web
cd $HOME/jity-web
rm -rf frontend
tar xzf $HOME/frontend-src.tgz
cd frontend
npm ci --no-audit --no-fund
mkdir -p public/models
if [ ! -s public/models/Qwen3-0.6B-Q4_K_M.gguf ]; then
  curl -L --retry 5 -o public/models/Qwen3-0.6B-Q4_K_M.gguf https://huggingface.co/unsloth/Qwen3-0.6B-GGUF/resolve/main/Qwen3-0.6B-Q4_K_M.gguf
fi
npm run build
npx playwright install chromium
echo SETUP_DONE
