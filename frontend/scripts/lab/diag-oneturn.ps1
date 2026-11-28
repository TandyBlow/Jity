param(
  [string]$Out = "artifacts/goal/lab",
  [int]$Port = 3177,
  [int]$TurnSeconds = 240
)

# One controlled diagnostic inside a single scheduler job: monitor + product
# server + one browser turn. Every child is started with UseShellExecute=false
# so it stays inside the caller's Job Object and dies with it.

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "../../..")).Path
Set-Location $root
$outDir = Join-Path $root $Out
New-Item -ItemType Directory -Force $outDir | Out-Null

function Start-Hidden([string]$file, [string]$arguments, [string]$workdir = $root) {
  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName = $file
  $psi.Arguments = $arguments
  $psi.WorkingDirectory = $workdir
  $psi.UseShellExecute = $false
  $psi.CreateNoWindow = $true
  return [System.Diagnostics.Process]::Start($psi)
}

$monitor = Start-Hidden "powershell.exe" "-NoProfile -ExecutionPolicy Bypass -File frontend/scripts/lab/monitor.ps1 -Out $outDir/diag-monitor.csv -Seconds 600"
Start-Sleep -Seconds 1

$server = Start-Hidden "cmd.exe" "/c node node_modules/next/dist/bin/next start -p $Port > `"$outDir\diag-server.log`" 2>&1" (Join-Path $root "frontend")

$ready = $false
for ($i = 0; $i -lt 120; $i++) {
  try {
    $r = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/world-local" -TimeoutSec 2
    if ($r.StatusCode -eq 200) { $ready = $true; break }
  } catch { }
  Start-Sleep -Seconds 1
}
"server ready=$ready after $i s" | Out-File -Append -Encoding utf8 "$outDir/diag.log"

if ($ready) {
  $turn = (Get-Content -Raw -Encoding utf8 (Join-Path $PSScriptRoot "diag-turn.txt")).Trim()
  & node frontend/scripts/memory-baseline.mjs "http://127.0.0.1:$Port/world-local?narrationModel=semantic&semanticCtx=8192" diag-oneturn "$outDir/diag-browser.jsonl" ($TurnSeconds * 1000) $turn
  "browser exit=$LASTEXITCODE" | Out-File -Append -Encoding utf8 "$outDir/diag.log"
}

if ($server -and -not $server.HasExited) { & taskkill /PID $server.Id /T /F | Out-Null }
if ($monitor -and -not $monitor.HasExited) { Stop-Process -Id $monitor.Id -Force -ErrorAction SilentlyContinue }
"swept server=$($server.Id) monitor=$($monitor.Id)" | Out-File -Append -Encoding utf8 "$outDir/diag.log"
