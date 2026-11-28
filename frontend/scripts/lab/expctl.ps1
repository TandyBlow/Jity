param(
  [Parameter(Mandatory=$true)][ValidateSet('submit','run','status','stop')][string]$Action,
  [string]$Name = "",
  [string]$Command = "",
  [string]$Cwd = "",
  [int]$BudgetMB = 4096,
  [int]$TimeoutSec = 1800,
  [int]$ReserveMB = 6144,
  [int]$HardFloorMB = 3072,
  [string]$KillMatch = "",
  [string]$Queue = "artifacts/goal/lab/queue.json",
  [string]$Active = "artifacts/goal/lab/active.json"
)

# Local experiment scheduler: one heavy job at a time, in a Windows Job Object
# with a commit cap and kill-on-close, gated on free RAM >= ReserveMB. Never
# touches processes outside its own job.

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "../../..")).Path
function FullPath($p) { if ([System.IO.Path]::IsPathRooted($p)) { $p } else { Join-Path $root $p } }
$Queue = FullPath $Queue
$Active = FullPath $Active
foreach ($f in @($Queue, $Active)) {
  $d = Split-Path -Parent $f
  if ($d -and -not (Test-Path $d)) { New-Item -ItemType Directory -Force $d | Out-Null }
}
if (-not (Test-Path $Queue)) { "[]" | Out-File -Encoding utf8 $Queue }

Add-Type @"
using System;
using System.Runtime.InteropServices;
public class JobObj {
  [StructLayout(LayoutKind.Sequential)] public struct IO_COUNTERS {
    public ulong ReadOperationCount, WriteOperationCount, OtherOperationCount;
    public ulong ReadTransferCount, WriteTransferCount, OtherTransferCount;
  }
  [StructLayout(LayoutKind.Sequential)] public struct BASIC {
    public long PerProcessUserTimeLimit, PerJobUserTimeLimit;
    public uint LimitFlags, MinimumWorkingSetSize, MaximumWorkingSetSize, ActiveProcessLimit;
    public UIntPtr Affinity; public uint PriorityClass, SchedulingClass;
  }
  [StructLayout(LayoutKind.Sequential)] public struct EXTENDED {
    public BASIC Basic; public IO_COUNTERS Io;
    public ulong ProcessMemoryLimit, JobMemoryLimit, PeakProcessMemoryUsed, PeakJobMemoryUsed;
  }
  [DllImport("kernel32.dll", CharSet=CharSet.Unicode)] public static extern IntPtr CreateJobObject(IntPtr a, string n);
  [DllImport("kernel32.dll")] public static extern bool SetInformationJobObject(IntPtr h, int cls, ref EXTENDED info, uint len);
  [DllImport("kernel32.dll")] public static extern bool AssignProcessToJobObject(IntPtr h, IntPtr p);
  [DllImport("kernel32.dll")] public static extern bool TerminateJobObject(IntPtr h, uint code);
  [DllImport("kernel32.dll")] public static extern bool CloseHandle(IntPtr h);
}
"@

function ReadJson($path, $fallback) {
  try { $raw = Get-Content -Raw -Encoding utf8 $path; if (-not $raw.Trim()) { return $fallback }; return ($raw | ConvertFrom-Json) }
  catch { return $fallback }
}
function WriteJson($path, $value) {
  if ($value -is [array]) {
    $parts = @($value | ForEach-Object { $_ | ConvertTo-Json -Depth 8 -Compress })
    ("[" + ($parts -join ",") + "]") | Out-File -Encoding utf8 $path
  } else { ($value | ConvertTo-Json -Depth 8) | Out-File -Encoding utf8 $path }
}
function Mem() {
  $os = Get-CimInstance Win32_OperatingSystem
  $perf = Get-CimInstance Win32_PerfRawData_PerfOS_Memory
  [pscustomobject]@{
    freeMB = [math]::Round($os.FreePhysicalMemory / 1KB)
    commitMB = [math]::Round($perf.CommittedBytes / 1MB)
    limitMB = [math]::Round($perf.CommitLimit / 1MB)
  }
}
function TreeMB($rootPid) {
  $all = Get-CimInstance Win32_Process | Select-Object ProcessId, ParentProcessId, WorkingSetSize
  $ids = @($rootPid); $frontier = @($rootPid)
  while ($frontier.Count -gt 0) {
    $next = @()
    foreach ($pidNum in $frontier) { $next += @($all | Where-Object { $_.ParentProcessId -eq $pidNum } | ForEach-Object { $_.ProcessId }) }
    $frontier = $next | Where-Object { $ids -notcontains $_ }
    $ids += $frontier
  }
  $sum = ($all | Where-Object { $ids -contains $_.ProcessId } | Measure-Object WorkingSetSize -Sum).Sum
  return [math]::Round($sum / 1MB)
}

if ($Action -eq 'submit') {
  if (-not $Name -or -not $Command) { throw "submit needs -Name and -Command" }
  $jobs = @(ReadJson $Queue @())
  $id = "job-" + (Get-Date -Format 'yyyyMMdd-HHmmss') + "-" + (Get-Random -Minimum 100 -Maximum 999)
  $jobs += [pscustomobject]@{
    id = $id; name = $Name; command = $Command; cwd = $(if ($Cwd) { $Cwd } else { "." })
    budgetMB = $BudgetMB; timeoutSec = $TimeoutSec; killMatch = $KillMatch; status = 'queued'
    submittedAt = (Get-Date).ToString('o'); startedAt = $null; endedAt = $null
    pid = $null; peakTreeMB = $null; log = "artifacts/goal/lab/$id.log"
  }
  WriteJson $Queue $jobs
  "queued $id $Name"
  exit 0
}

if ($Action -eq 'status') {
  ReadJson $Queue @() | Format-Table id, name, status, budgetMB, timeoutSec, startedAt, endedAt -AutoSize | Out-String
  if (Test-Path $Active) { "active: " + (Get-Content -Raw $Active) }
  exit 0
}

if ($Action -eq 'stop') {
  $a = ReadJson $Active $null
  if ($a -and $a.pid) {
    & taskkill /PID $a.pid /T /F | Out-Null
    $a.status = 'stopped'
    WriteJson $Active $a
    "stopped " + $a.pid
  } else { "no active job" }
  exit 0
}

# run
while ($true) {
  $jobs = @(ReadJson $Queue @())
  $job = $jobs | Where-Object { $_.status -eq 'queued' } | Select-Object -First 1
  if (-not $job) { "queue empty"; break }

  while ($true) {
    $m = Mem
    if ($m.freeMB -ge $ReserveMB -and ($m.limitMB - $m.commitMB) -ge 4096) { break }
    "deferred {0}: freeMB={1} commitMB={2}/{3}" -f $job.name, $m.freeMB, $m.commitMB, $m.limitMB
    Start-Sleep -Seconds 15
    $jobs = @(ReadJson $Queue @())
    $job = $jobs | Where-Object { $_.id -eq $job.id } | Select-Object -First 1
    if (-not $job -or $job.status -ne 'queued') { break }
  }
  if (-not $job -or $job.status -ne 'queued') { continue }

  $logPath = FullPath $job.log
  $workDir = FullPath $job.cwd
  $job.status = 'running'; $job.startedAt = (Get-Date).ToString('o')
  $idx = [array]::IndexOf($jobs, ($jobs | Where-Object { $_.id -eq $job.id } | Select-Object -First 1))
  WriteJson $Queue $jobs

  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName = "cmd.exe"
  $psi.Arguments = "/c " + $job.command + " > `"$logPath`" 2>&1"
  $psi.WorkingDirectory = $workDir
  $psi.UseShellExecute = $false
  $psi.CreateNoWindow = $true
  $proc = [System.Diagnostics.Process]::Start($psi)

  $jobHandle = [JobObj]::CreateJobObject([IntPtr]::Zero, $null)
  $info = New-Object JobObj+EXTENDED
  $flags = [uint32]0x2000 -bor 0x100 -bor 0x200   # kill-on-close | process memory | job memory
  $info.Basic.LimitFlags = $flags
  $bytes = [uint64]($job.budgetMB * 1MB)
  $info.ProcessMemoryLimit = $bytes
  $info.JobMemoryLimit = $bytes
  [JobObj]::SetInformationJobObject($jobHandle, 9, [ref]$info, [uint32][System.Runtime.InteropServices.Marshal]::SizeOf($info)) | Out-Null
  [JobObj]::AssignProcessToJobObject($jobHandle, $proc.Handle) | Out-Null

  [pscustomobject]@{ id = $job.id; name = $job.name; pid = $proc.Id; status = 'running'; startedAt = $job.startedAt } | Out-File -Encoding utf8 $Active

  $start = Get-Date; $peak = 0; $reason = 'exited'
  $seen = @{}
  while (-not $proc.HasExited) {
    $tree = TreeMB $proc.Id
    if ($tree -gt $peak) { $peak = $tree }
    $snap = Get-CimInstance Win32_Process | Select-Object ProcessId, ParentProcessId, CreationDate
    $frontier = @($proc.Id); $ids = @($proc.Id)
    while ($frontier.Count -gt 0) {
      $next = @()
      foreach ($pidNum in $frontier) { $next += @($snap | Where-Object { $_.ParentProcessId -eq $pidNum } | ForEach-Object { $_.ProcessId }) }
      $frontier = $next | Where-Object { $ids -notcontains $_ }
      $ids += $frontier
    }
    foreach ($id in $ids) {
      $row = $snap | Where-Object { $_.ProcessId -eq $id } | Select-Object -First 1
      if ($row -and $id -ne $proc.Id) { $seen[[int]$id] = $row.CreationDate }
    }
    $m = Mem
    if ($m.freeMB -lt $HardFloorMB) { $reason = 'hard-floor'; break }
    if (((Get-Date) - $start).TotalSeconds -gt $job.timeoutSec) { $reason = 'timeout'; break }
    Start-Sleep -Seconds 1
  }
  if (-not $proc.HasExited) { [JobObj]::TerminateJobObject($jobHandle, 1) | Out-Null }
  # safety net: descendants that escaped the job (ShellExecute) are killed by pid+creation time
  if ($job.killMatch) {
    $since = [datetime]$start
    Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like ("*" + $job.killMatch + "*") -and $_.CreationDate -ge $since } | ForEach-Object {
      Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
      "matched-kill " + $_.ProcessId
    }
  }
  foreach ($key in @($seen.Keys)) {
    $alive = Get-CimInstance Win32_Process -Filter ("ProcessId=" + $key) -ErrorAction SilentlyContinue
    if ($alive -and $alive.CreationDate -eq $seen[$key]) {
      Stop-Process -Id $key -Force -ErrorAction SilentlyContinue
      "swept " + $key
    }
  }
  Start-Sleep -Milliseconds 500
  [JobObj]::CloseHandle($jobHandle) | Out-Null

  $jobs = @(ReadJson $Queue @())
  foreach ($j in $jobs) {
    if ($j.id -eq $job.id) {
      $j.status = $(if ($reason -eq 'exited') { 'done' } else { $reason })
      $j.endedAt = (Get-Date).ToString('o'); $j.peakTreeMB = $peak
      if (-not $j.pid) { $j | Add-Member -NotePropertyName pid -NotePropertyValue $proc.Id -Force }
    }
  }
  WriteJson $Queue $jobs
  Remove-Item $Active -ErrorAction SilentlyContinue
  "finished {0} status={1} peakTreeMB={2}" -f $job.name, $reason, $peak
}
