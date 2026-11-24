#!/usr/bin/env bash
# Browser matrix: 2 precisions x 3 lengths x 1/4 threads, ORT-WASM.
set -u
cd /d/others/Jity/.local/probe-transformers
cp -f /d/others/Jity/.local/micro-quant/shared-split.onnx models/
cp -f /d/others/Jity/.local/micro-quant/shared-split-int8.onnx models/
SRV=
if ! curl -s -o /dev/null http://127.0.0.1:3190/probe/micro-encoder.html; then
  node server.mjs >/tmp/probe-quant.log 2>&1 &
  SRV=$!
  curl -s --retry 30 --retry-connrefused --retry-delay 1 -o /dev/null http://127.0.0.1:3190/probe/micro-encoder.html || true
fi
OUT=/d/others/Jity/artifacts/goal/micro-quant/browser.log
: > "$OUT"
for model in shared-split shared-split-int8; do
  for n in 32 128 512; do
    for t in 1 4; do
      node run.mjs --url="http://127.0.0.1:3190/probe/micro-encoder.html?model=$model&sample=quant-$n&threads=$t&ep=wasm" >> "$OUT" 2>&1
    done
  done
done
[ -n "$SRV" ] && kill "$SRV"
echo done
