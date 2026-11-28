$ErrorActionPreference = 'Continue'
$root = 'D:\others\Jity'
Set-Location $root
$serverLog = Join-Path $root 'artifacts/goal/platform/lab/server-3179.log'
$node = Start-Process node -ArgumentList 'node_modules/next/dist/bin/next', 'start', '-p', '3179' `
  -WorkingDirectory (Join-Path $root 'frontend') -RedirectStandardOutput $serverLog `
  -RedirectStandardError ($serverLog + '.err') -PassThru -WindowStyle Hidden
try {
  $ok = $false
  for ($i = 0; $i -lt 45; $i++) {
    try {
      $r = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:3179/world-local' -TimeoutSec 2
      if ($r.StatusCode -eq 200) { $ok = $true; break }
    } catch {}
    Start-Sleep -Seconds 2
  }
  if (-not $ok) { 'server-failed'; exit 2 }
  'server-ready'
  Set-Location (Join-Path $root 'frontend')
  node scripts/product-acceptance/accept-world-local.mjs --base http://127.0.0.1:3179 `
    --turns ../artifacts/goal/platform/eval/turns-holdout-v1.json `
    --profile ../artifacts/goal/lab/holdout-profile5 --fresh `
    --query 'semanticCtx=4096&narrationModel=semantic' `
    --out ../results/product/evidence/holdout-v1f-20261128.json --turn-timeout-ms 600000 `
    2>&1 | Tee-Object -FilePath ../artifacts/goal/platform/lab/holdout-v1f.log
  "driver-exit=$LASTEXITCODE"
} finally {
  if ($node) { & taskkill /PID $node.Id /T /F | Out-Null }
}
