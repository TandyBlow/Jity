$ErrorActionPreference = 'Continue'
$root = 'D:\others\Jity'
Set-Location $root
$tmp = Join-Path $root 'artifacts/goal/platform/lab-ab'
if (Test-Path $tmp) { Get-ChildItem $tmp | Remove-Item -Recurse -Force }
New-Item -ItemType Directory -Force $tmp | Out-Null
$old = Join-Path $tmp 'old-expctl.ps1'
git -C $root show e2ab4f08:frontend/scripts/lab/expctl.ps1 | Out-File -Encoding utf8 $old
$new = Join-Path $root 'frontend/scripts/lab/expctl.ps1'

function Run-Lock($script, $tag) {
  $q = Join-Path $tmp "$tag-queue.json"; '[]' | Out-File -Encoding utf8 $q
  $lock = Join-Path (Split-Path -Parent $q) 'run.lock'
  Set-Content -Encoding utf8 $lock '999999'
  $sw = [Diagnostics.Stopwatch]::StartNew()
  & powershell -NoProfile -File $script -Action run -Queue $q -Active (Join-Path $tmp "$tag-active.json") *> $null
  $code = $LASTEXITCODE
  $sw.Stop()
  Remove-Item $lock -Force -ErrorAction SilentlyContinue
  [pscustomobject]@{ tag = $tag; exit = $code; ms = [math]::Round($sw.Elapsed.TotalMilliseconds) }
}

function Run-Submits($script, $tag, $n) {
  $q = Join-Path $tmp "$tag-submit.json"; '[]' | Out-File -Encoding utf8 $q
  $active = Join-Path $tmp "$tag-submit-active.json"
  $procs = @()
  for ($i = 1; $i -le $n; $i++) {
    $a = @('-NoProfile', '-File', $script, '-Action', 'submit',
           '-Name', "j$i", '-Command', 'exit', '-Queue', $q, '-Active', $active)
    $procs += Start-Process powershell -ArgumentList $a -PassThru -WindowStyle Hidden
  }
  $procs | Wait-Process
  try { $count = @((Get-Content -Raw -Encoding utf8 $q | ConvertFrom-Json)).Count } catch { $count = -1 }
  [pscustomobject]@{ tag = $tag; expected = $n; queued = $count }
}

$oldLock = Run-Lock $old 'old'
$newLock = Run-Lock $new 'new'
$oldSub = Run-Submits $old 'old' 30
$newSub = Run-Submits $new 'new' 30
[pscustomobject]@{ lock = @($oldLock, $newLock); submit = @($oldSub, $newSub) } |
  ConvertTo-Json -Depth 5 | Tee-Object (Join-Path $tmp 'report.json')
