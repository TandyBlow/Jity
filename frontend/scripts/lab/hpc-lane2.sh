#!/bin/bash
set -x
export PATH=$HOME/node20/node-v20.18.1-linux-x64/bin:$PATH
cd $HOME/jity-web/frontend
PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright npx playwright install chromium --only-shell
echo PW_EXIT=$?
mkdir -p public/models
curl -L --retry 5 -o public/models/Qwen3-0.6B-Q4_K_M.gguf https://hf-mirror.com/unsloth/Qwen3-0.6B-GGUF/resolve/main/Qwen3-0.6B-Q4_K_M.gguf
echo HF_EXIT=$?
ls -la public/models/*.gguf
