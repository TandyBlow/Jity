#!/usr/bin/env bash
# In-browser pair evaluation: same int8 model, same tokenized inputs, accuracy + latency.
set -u
cd /d/others/Jity/.local/probe-transformers
cp -f /d/others/Jity/.local/micro-generalize/pair-scorer.onnx models/
cp -f /d/others/Jity/.local/micro-generalize/pair-scorer-int8.onnx models/
cp -f /d/others/Jity/artifacts/goal/micro-generalize/pairs.html .
SRV=
if ! curl -s -o /dev/null http://127.0.0.1:3190/probe/pairs.html; then
  node server.mjs >/tmp/probe-pairs.log 2>&1 &
  SRV=$!
  curl -s --retry 30 --retry-connrefused --retry-delay 1 -o /dev/null http://127.0.0.1:3190/probe/pairs.html || true
fi
OUT=/d/others/Jity/artifacts/goal/micro-generalize/browser.log
: > "$OUT"
node run.mjs --url="http://127.0.0.1:3190/probe/pairs.html?model=pair-scorer-int8&threads=4&ep=wasm" >> "$OUT" 2>&1
node run.mjs --url="http://127.0.0.1:3190/probe/pairs.html?model=pair-scorer-int8&threads=1&ep=wasm" >> "$OUT" 2>&1
[ -n "$SRV" ] && kill "$SRV"
echo done
