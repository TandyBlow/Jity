#!/bin/bash
set -e
mkdir -p ~/qwen05b
cd ~/qwen05b
for f in config.json generation_config.json model.safetensors tokenizer.json tokenizer_config.json vocab.json merges.txt; do
  [ -s "$f" ] || curl -L --fail --retry 3 -sS -o "$f" "https://www.modelscope.cn/models/Qwen/Qwen2.5-0.5B-Instruct/resolve/master/$f"
done
ls -lh
