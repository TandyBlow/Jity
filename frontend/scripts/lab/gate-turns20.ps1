param(
  [int]$Port = 3177,
  [string]$Query = "semanticCtx=8192&narrationModel=semantic",
  [string]$Out = "../results/product/evidence/09-turns20-ctx8192-gpu-run3.json",
  [string]$Log = "../results/product/evidence/09-turns20-ctx8192-gpu-run3.log"
)

# 20-input acceptance inside one scheduler job: start the product server if
# needed, run the harness with a single --query argument (no cmd & split),
# then stop the server we started.
$ErrorActionPreference = "Continue"
$root = (Resolve-Path (Join-Path $PSScriptRoot "../../..")).Path
Set-Location $root
$frontend = Join-Path $root "frontend"

function Start-Hidden([string]$file, [string]$arguments, [string]$workdir) {
  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName = $file; $psi.Arguments = $arguments; $psi.WorkingDirectory = $workdir
  $psi.UseShellExecute = $false; $psi.CreateNoWindow = $true
  return [System.Diagnostics.Process]::Start($psi)
}

$server = $null
$up = $false
try { $r = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/world-local" -TimeoutSec 2; $up = ($r.StatusCode -eq 200) } catch { }
if (-not $up) {
  $server = Start-Hidden "cmd.exe" "/c node node_modules/next/dist/bin/next start -p $Port > `"$root\artifacts\goal\lab\gate-server.log`" 2>&1" $frontend
  for ($i = 0; $i -lt 120; $i++) {
    try { $r = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/world-local" -TimeoutSec 2; if ($r.StatusCode -eq 200) { $up = $true; break } } catch { }
    Start-Sleep -Seconds 1
  }
}
"server up=$up" | Out-File -Append -Encoding utf8 "$root/artifacts/goal/lab/gate.log"

if ($up) {
  Push-Location $frontend
  & node scripts/product-acceptance/accept-world-local.mjs --base "http://127.0.0.1:$Port" --turns scripts/product-acceptance/turns-20.json --out $Out --fresh --query $Query *> $Log
  "harness exit=$LASTEXITCODE" | Out-File -Append -Encoding utf8 "$root/artifacts/goal/lab/gate.log"
  Pop-Location
}

if ($server -and -not $server.HasExited) { & taskkill /PID $server.Id /T /F | Out-Null }
"done server=$($server.Id)" | Out-File -Append -Encoding utf8 "$root/artifacts/goal/lab/gate.log"
