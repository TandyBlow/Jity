param([string]$Out = "process-memory.csv", [int]$Seconds = 180)
"t,freeMB,edgeMB,edgeProcs" | Out-File -Encoding utf8 $Out
$start = Get-Date
while (((Get-Date) - $start).TotalSeconds -lt $Seconds) {
  $os = Get-CimInstance Win32_OperatingSystem
  $edge = Get-Process msedge -ErrorAction SilentlyContinue
  $edgeMB = if ($edge) { [math]::Round((($edge | Measure-Object WorkingSet64 -Sum).Sum)/1MB) } else { 0 }
  $procs = if ($edge) { ($edge | Measure-Object).Count } else { 0 }
  $t = [math]::Round(((Get-Date) - $start).TotalSeconds)
  "$t,$([math]::Round($os.FreePhysicalMemory / 1KB, 0)),$edgeMB,$procs" | Out-File -Append -Encoding utf8 $Out
  Start-Sleep -Seconds 2
}
