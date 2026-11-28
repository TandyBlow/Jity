param(
  [string]$Stages = "page,fetch,init:2048",
  [int]$Port = 3177,
  [int]$Seconds = 90,
  [string]$Out = "artifacts/goal/lab"
)

# Runs the staged load probe for each stage in a fresh profile, inside one
# scheduler job: page -> GGUF fetch -> wllama init -> first inference.
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "../../..")).Path
Set-Location $root
$outDir = Join-Path $root $Out
New-Item -ItemType Directory -Force $outDir | Out-Null

function Start-Hidden([string]$file, [string]$arguments, [string]$workdir) {
  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName = $file; $psi.Arguments = $arguments; $psi.WorkingDirectory = $workdir
  $psi.UseShellExecute = $false; $psi.CreateNoWindow = $true
  return [System.Diagnostics.Process]::Start($psi)
}

$server = $null
$up = $false
try { $r = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/lab-load?stage=page" -TimeoutSec 2; $up = ($r.StatusCode -eq 200) } catch { }
if (-not $up) {
  $server = Start-Hidden "cmd.exe" "/c node node_modules/next/dist/bin/next start -p $Port > `"$outDir\load-server.log`" 2>&1" (Join-Path $root "frontend")
  for ($i = 0; $i -lt 120; $i++) {
    try { $r = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/lab-load?stage=page" -TimeoutSec 2; if ($r.StatusCode -eq 200) { $up = $true; break } } catch { }
    Start-Sleep -Seconds 1
  }
}
"server up=$up" | Out-File -Append -Encoding utf8 "$outDir/load-stages.log"

if ($up) {
  foreach ($spec in $Stages.Split(",")) {
    $parts = $spec.Split(":")
    $stage = $parts[0]
    $ctx = if ($parts.Length -gt 1) { [int]$parts[1] } else { 2048 }
    $nb = if ($parts.Length -gt 2) { [int]$parts[2] } else { 0 }
    $file = "$outDir/load-$stage-$ctx-$nb.jsonl"
    & node frontend/scripts/lab/load-probe.mjs $stage $ctx $file ($Seconds * 1000) $nb
    "stage=$stage ctx=$ctx nb=$nb exit=$LASTEXITCODE" | Out-File -Append -Encoding utf8 "$outDir/load-stages.log"
  }
}

if ($server -and -not $server.HasExited) { & taskkill /PID $server.Id /T /F | Out-Null }
"done server=$($server.Id)" | Out-File -Append -Encoding utf8 "$outDir/load-stages.log"
