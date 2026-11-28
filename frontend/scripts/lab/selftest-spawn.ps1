$child = "Set-Content -Path artifacts/goal/lab/spawn-child-start.txt -Value started; Start-Sleep -Seconds 120; Set-Content -Path artifacts/goal/lab/spawn-child-end.txt -Value ended"
Start-Process powershell -ArgumentList '-NoProfile','-Command',$child
Write-Output spawned
