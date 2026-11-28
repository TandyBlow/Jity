param(
  [int]$Port = 3177,
  [string]$Profile = "artifacts/goal/lab/gate-profile",
  [string]$Out = "../results/product/evidence/09-turns20-ctx8192-gpu-run5.json",
  [string]$Log = "../results/product/evidence/09-turns20-ctx8192-gpu-run5.log",
  [int]$Attempts = 6
)

# 20-input gate across memory windows: one persistent browser profile keeps
# the IndexedDB save, and each attempt resumes after the last recorded turn.
# The Job Object still bounds the whole job's memory.
$ErrorActionPreference = "Continue"
$root = (Resolve-Path (Join-Path $PSScriptRoot "../../..")).Path
Set-Location $root
$frontend = Join-Path $root "frontend"
$profileDir = Join-Path $root $Profile
New-Item -ItemType Directory -Force $profileDir | Out-Null
New-Item -ItemType Directory -Force (Split-Path -Parent (Join-Path $root $Out)) | Out-Null

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
"resume-gate server up=$up" | Out-File -Append -Encoding utf8 "$root/artifacts/goal/lab/gate.log"

if ($up) {
  Push-Location $frontend
  for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
    $resume = if (Test-Path (Join-Path $root $Out)) { '--resume' } else { '--fresh' }
    & node scripts/product-acceptance/accept-world-local.mjs --base "http://127.0.0.1:$Port" --turns scripts/product-acceptance/turns-20.json --out $Out --profile $Profile $resume --query "semanticCtx=8192&narrationModel=semantic" *> $Log
    $status = 'UNKNOWN'
    try { $status = (Get-Content -Raw (Join-Path $root $Out) | ConvertFrom-Json).status } catch { }
    "attempt $attempt status=$status" | Out-File -Append -Encoding utf8 "$root/artifacts/goal/lab/gate.log"
    if ($status -eq 'COMPLETED') { break }
    if ($status -eq 'FAILED') { break }   # a failed turn is a gate failure, not a kill
  }
  Pop-Location
}

if ($server -and -not $server.HasExited) { & taskkill /PID $server.Id /T /F | Out-Null }
"resume-gate done server=$($server.Id)" | Out-File -Append -Encoding utf8 "$root/artifacts/goal/lab/gate.log"
