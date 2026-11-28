param(
  [string]$Stage = "init",
  [int]$Ctx = 2048,
  [int]$Nb = 2048,
  [int]$PromptLen = 0,
  [int]$Direct = 0,
  [string]$Kv = "q8_0",
  [int]$Port = 3180,
  [int]$Seconds = 180
)
$Query = "stage=$Stage&ctx=$Ctx&nb=$Nb&promptLen=$PromptLen&direct=$Direct&kv=$Kv"

$ErrorActionPreference = "Continue"
$root = (Resolve-Path (Join-Path $PSScriptRoot "../../..")).Path
Set-Location $root
$pub = Join-Path $root "frontend/public"
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = "python"; $psi.Arguments = "-m http.server $Port --directory `"$pub`""
$psi.WorkingDirectory = $root; $psi.UseShellExecute = $false; $psi.CreateNoWindow = $true
$server = [System.Diagnostics.Process]::Start($psi)
$up = $false
for ($i = 0; $i -lt 60; $i++) {
  try { $r = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/lab-static.html" -TimeoutSec 2; if ($r.StatusCode -eq 200) { $up = $true; break } } catch { }
  Start-Sleep -Milliseconds 500
}
"static up=$up" | Out-File -Append -Encoding utf8 "$root/artifacts/goal/lab/static.log"
if ($up) {
  & node frontend/scripts/lab/static-probe.mjs "http://127.0.0.1:$Port/lab-static.html?$Query" $Seconds *>> "$root/artifacts/goal/lab/static.log"
  "probe exit=$LASTEXITCODE" | Out-File -Append -Encoding utf8 "$root/artifacts/goal/lab/static.log"
}
if ($server -and -not $server.HasExited) { Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue }
exit 0
