#!/bin/bash
set -euo pipefail
export PATH=$HOME/node20/node-v20.18.1-linux-x64/bin:$PATH
cd $HOME
if [ ! -d jity-web ]; then git clone --depth 1 -b agent https://github.com/TandyBlow/Jity.git jity-web; else cd jity-web && git pull --ff-only; cd $HOME; fi
cd $HOME/jity-web/frontend
npm ci --no-audit --no-fund
mkdir -p public/models public/wllama public/wasm
if [ ! -s public/models/Qwen3-0.6B-Q4_K_M.gguf ]; then curl -L --retry 5 -o public/models/Qwen3-0.6B-Q4_K_M.gguf https://huggingface.co/unsloth/Qwen3-0.6B-GGUF/resolve/main/Qwen3-0.6B-Q4_K_M.gguf; fi
npm run build
npx playwright install chromium
echo SETUP_DONE
