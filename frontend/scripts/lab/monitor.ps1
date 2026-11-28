param(
  [string]$Out = "artifacts/goal/lab/monitor.csv",
  [int]$Seconds = 300,
  [string]$Tag = "",
  [int]$GpuEvery = 5
)

# Per-second resource record (PS 5.1 compatible): free/commit/pagefile plus
# Edge/Node/Python/Next processes and GPU process memory counters. Rows are
# appended immediately, so a kill never loses the trace.

$ErrorActionPreference = "SilentlyContinue"
$dir = Split-Path -Parent $Out
if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Force $dir | Out-Null }
$header = "t,kind,pid,ppid,name,privateMB,wsMB,freeMB,commitMB,limitMB,pagefileMB,gpuDedicatedMB,gpuSharedMB,cmd"
$header | Out-File -Encoding utf8 $Out

$start = Get-Date
$info = @{}
$lastRefresh = -100
while (((Get-Date) - $start).TotalSeconds -lt $Seconds) {
  $t = [math]::Round(((Get-Date) - $start).TotalSeconds, 0)
  $os = Get-CimInstance Win32_OperatingSystem
  $perf = Get-CimInstance Win32_PerfRawData_PerfOS_Memory
  $pf = (Get-CimInstance Win32_PageFileUsage | Select-Object -First 1).CurrentUsage
  $free = [math]::Round($os.FreePhysicalMemory / 1KB)
  $commit = [math]::Round($perf.CommittedBytes / 1MB)
  $limit = [math]::Round($perf.CommitLimit / 1MB)

  if ($t - $lastRefresh -ge 10) {
    $info = @{}
    Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('msedge.exe','node.exe','python.exe','python3.exe','chrome.exe') } | ForEach-Object {
      $info[[int]$_.ProcessId] = @{ ppid = [int]$_.ParentProcessId; cmd = $_.CommandLine }
    }
    $lastRefresh = $t
  }

  $procs = Get-Process | Where-Object { $_.ProcessName -in @('msedge','node','python','python3','chrome','next') }
  foreach ($p in $procs) {
    $meta = $info[[int]$p.Id]
    $cmd = ""
    $ppid = ""
    if ($meta) { $cmd = ($meta.cmd -replace '[,\r\n]', ' '); $ppid = $meta.ppid }
    if ($Tag -and ($cmd -notlike "*$Tag*")) { continue }
    [pscustomobject]@{
      t = $t; kind = 'proc'; pid = $p.Id; ppid = $ppid; name = $p.ProcessName
      privateMB = [math]::Round($p.PrivateMemorySize64 / 1MB); wsMB = [math]::Round($p.WorkingSet64 / 1MB)
      freeMB = $free; commitMB = $commit; limitMB = $limit; pagefileMB = $pf
      gpuDedicatedMB = ''; gpuSharedMB = ''; cmd = $cmd
    } | Export-Csv -Append -NoTypeInformation -Encoding utf8 $Out
  }

  if ($t % $GpuEvery -eq 0) {
    $ded = Get-Counter '\GPU Process Memory(*)\Dedicated Usage' | Select-Object -ExpandProperty CounterSamples
    $shr = Get-Counter '\GPU Process Memory(*)\Shared Usage' | Select-Object -ExpandProperty CounterSamples
    $gpu = @{}
    foreach ($s in $ded) { if ($s.InstanceName -match 'pid_(\d+)') { $gpu[[int]$Matches[1]] = @{ d = [math]::Round($s.CookedValue / 1MB); s = 0 } } }
    foreach ($s in $shr) { if ($s.InstanceName -match 'pid_(\d+)') { $pidNum = [int]$Matches[1]; if (-not $gpu[$pidNum]) { $gpu[$pidNum] = @{ d = 0; s = 0 } }; $gpu[$pidNum].s = [math]::Round($s.CookedValue / 1MB) } }
    foreach ($key in $gpu.Keys) {
      [pscustomobject]@{
        t = $t; kind = 'gpu'; pid = $key; ppid = ''; name = ''
        privateMB = ''; wsMB = ''; freeMB = $free; commitMB = $commit; limitMB = $limit; pagefileMB = $pf
        gpuDedicatedMB = $gpu[$key].d; gpuSharedMB = $gpu[$key].s; cmd = ''
      } | Export-Csv -Append -NoTypeInformation -Encoding utf8 $Out
    }
  }

  Start-Sleep -Milliseconds 1000
}
