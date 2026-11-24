#!/usr/bin/env bash
# Run the 0.6B arm for the given chunk start indices.
set -u
cd /d/others/Jity/.local/probe-transformers
cp -f /d/others/Jity/artifacts/goal/micro-eval/eval-06b.html .
SRV=
if ! curl -s -o /dev/null http://127.0.0.1:3190/probe/eval-06b.html; then
  node server.mjs >/tmp/probe-06b.log 2>&1 &
  SRV=$!
  curl -s --retry 30 --retry-connrefused --retry-delay 1 -o /dev/null http://127.0.0.1:3190/probe/eval-06b.html || true
fi
OUT=/d/others/Jity/artifacts/goal/micro-eval/eval-06b.log
for start in "$@"; do
  node run.mjs --url="http://127.0.0.1:3190/probe/eval-06b.html?start=$start&size=25" >> "$OUT" 2>&1
done
[ -n "$SRV" ] && kill "$SRV"
echo done
