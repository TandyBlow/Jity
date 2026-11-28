#!/bin/bash
# HPC browser lane: start the product from the uploaded build, run one
# acceptance fixture headless with the bundled Chromium, stop the server.
set -euo pipefail
export PATH=$HOME/node20/node-v20.18.1-linux-x64/bin:$PATH
export PW_CHANNEL=chromium
TURNS=${1:-scripts/product-acceptance/turns-smoke1.json}
OUT=${2:-../results/product/evidence/10-hpc-smoke.json}
cd $HOME/jity-web/frontend
mkdir -p $HOME/jity-web/results/product/evidence
node node_modules/next/dist/bin/next start -p 3177 > $HOME/jity-web/gate-server.log 2>&1 &
SERVER=$!
trap "kill $SERVER 2>/dev/null || true" EXIT
for i in $(seq 1 90); do
  if curl -sf -o /dev/null http://127.0.0.1:3177/world-local; then break; fi
  sleep 1
done
node scripts/product-acceptance/accept-world-local.mjs --base http://127.0.0.1:3177 --turns "$TURNS" --out "$OUT" --fresh --query "semanticCtx=8192&narrationModel=semantic&cpu=1"
echo GATE_EXIT=$?
