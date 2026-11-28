#!/bin/bash
# Memory arms after the ctx gate: each opens a fresh profile, loads the 0.6B
# engine, runs one fixture turn, and samples page-attributed memory.
set -u
cd "$(dirname "$0")/../../.." || exit 1
OUT=artifacts/goal/memory-baseline
BASE='http://127.0.0.1:3177/world-local'
TURN='我沿着服务巷的墙根往器材棚方向走，脚步放轻，注意前面的门口。'
ARMS=(
  "12288_q8|semanticCtx=12288&kv=q8_0"
  "8192_q8|semanticCtx=8192&kv=q8_0"
  "4096_q8|semanticCtx=4096&kv=q8_0"
  "8192_q4|semanticCtx=8192&kv=q4_0"
  "8192_nb256|semanticCtx=8192&kv=q8_0&nbatch=256"
  "4096_q4_nb256|semanticCtx=4096&kv=q4_0&nbatch=256"
)
for arm in "${ARMS[@]}"; do
  name="${arm%%|*}"
  query="${arm#*|}"
  echo "[arm] $name $query"
  node frontend/scripts/memory-baseline.mjs \
    "$BASE?narrationModel=semantic&$query" "$name" "$OUT/arm-$name.jsonl" 300000 "$TURN" \
    > "$OUT/arm-$name.log" 2>&1
  echo "[arm] $name exit=$?"
done
