#!/usr/bin/env bash
# Speed sweep for T2: fp32/int8 x 8/16/32/64/128 tokens x 1/4 threads.
set -u
cd /d/others/Jity/.local/probe-transformers
cp -f /d/others/Jity/.local/micro-joint/t2.onnx models/joint-t2.onnx
cp -f /d/others/Jity/.local/micro-joint/t2-int8.onnx models/joint-t2-int8.onnx
SRV=
if ! curl -s -o /dev/null http://127.0.0.1:3190/probe/micro-encoder.html; then
  node server.mjs >/tmp/probe-joint.log 2>&1 &
  SRV=$!
  curl -s --retry 30 --retry-connrefused --retry-delay 1 -o /dev/null http://127.0.0.1:3190/probe/micro-encoder.html || true
fi
OUT=/d/others/Jity/artifacts/goal/micro-joint/browser-lengths.log
: > "$OUT"
for model in joint-t2 joint-t2-int8; do
  for n in 8 16 32 64 128; do
    for t in 1 4; do
      node run.mjs --url="http://127.0.0.1:3190/probe/micro-encoder.html?model=$model&sample=joint-$n&threads=$t&ep=wasm" >> "$OUT" 2>&1
    done
  done
done
[ -n "$SRV" ] && kill "$SRV"
echo done
