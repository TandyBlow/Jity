$ErrorActionPreference = 'Continue'
$root = 'D:\others\Jity'
Set-Location $root
$env:PYTHONUTF8 = '1'
$evidence = 'results/product/evidence/holdout-v1c-20261128.json'
for ($i = 0; $i -lt 30; $i++) {
  $lease = (& python -X utf8 resource_lease.py status) | ConvertFrom-Json
  $free = [math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1KB)
  "$(Get-Date -Format o) try=$i lease=$($lease.status) freeMB=$free"
  if ($lease.status -eq 'free' -and $free -ge 2800) {
    if (Test-Path $evidence) { Copy-Item $evidence "$evidence.attempt$i.json" -Force }
    & .\frontend\scripts\lab\expctl.ps1 -Action submit -Name holdout-v1c -Command 'node scripts/product-acceptance/accept-world-local.mjs --base http://127.0.0.1:3177 --turns ../artifacts/goal/platform/eval/turns-holdout-v1.json --profile ../artifacts/goal/lab/holdout-profile3 --fresh --query "semanticCtx=4096&narrationModel=semantic" --out ../results/product/evidence/holdout-v1c-20261128.json --turn-timeout-ms 600000' -Cwd frontend -BudgetMB 4096 -TimeoutSec 1200
    & .\frontend\scripts\lab\expctl.ps1 -Action run -ReserveMB 1200 -ExpectMB 1200
    if (Test-Path $evidence) {
      $doc = Get-Content -Raw $evidence | ConvertFrom-Json
      "attempt $i status=$($doc.status) turns=$($doc.turns.Count) failures=$($doc.failures.Count)"
      if ($doc.turns.Count -ge 1) { exit 0 }
    }
  }
  Start-Sleep -Seconds 20
}
exit 1
