param([Parameter(Mandatory=$true)][string]$OutputDirectory,
      [Parameter(Mandatory=$true)][string]$BoardPlan,
      [string]$PortName='COM3')
$ErrorActionPreference='Stop'
if ($BoardPlan -notmatch '^/tmp/person_demo_[A-Za-z0-9_]+\.json$') {throw 'Session plan path required'}
if (Test-Path -LiteralPath $OutputDirectory) {throw 'Use a new private evidence directory'}
$taskPython=Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$taskGuard=Join-Path $PSScriptRoot 'person_demo_camera_guard.py'
$taskCapture=Start-Process -FilePath $taskPython -ArgumentList @($taskGuard,$OutputDirectory) -WindowStyle Hidden -PassThru
$taskSerial=[IO.Ports.SerialPort]::new($PortName,115200,[IO.Ports.Parity]::None,8,[IO.Ports.StopBits]::One)
$taskSerial.DtrEnable=$false;$taskSerial.RtsEnable=$false;$taskSerial.WriteTimeout=500
$taskOff=$false;$taskComplete=$false;$taskStarted=$false;$taskInterrupted=$false
$taskReason=$null;$taskRaw=$null;$taskEvents=$null
function Test-DemoViews {
    if ($taskCapture.HasExited -or (Test-Path -LiteralPath (Join-Path $OutputDirectory 'guard.error')) -or
        (Test-Path -LiteralPath (Join-Path $OutputDirectory 'stop.request'))) {return $false}
    $leasePath=Join-Path $OutputDirectory 'lease.json'
    if (-not (Test-Path -LiteralPath $leasePath)) {return $false}
    try {
        $value=Get-Content -LiteralPath $leasePath -Raw | ConvertFrom-Json
        $age=[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()-[long]$value.unix_ms
        return ($age -ge 0 -and $age -lt 800)
    } catch {return $false}
}
try {
    $readyUntil=[DateTime]::UtcNow.AddSeconds(5)
    while (-not (Test-DemoViews) -and [DateTime]::UtcNow -lt $readyUntil) {Start-Sleep -Milliseconds 80}
    if (-not (Test-DemoViews)) {throw 'Two advancing camera streams not ready; no serial motion sent'}
    $taskRaw=[IO.StreamWriter]::new((Join-Path $OutputDirectory 'board.log'),$false,[Text.UTF8Encoding]::new($false))
    $taskEvents=[IO.StreamWriter]::new((Join-Path $OutputDirectory 'events.jsonl'),$false,[Text.UTF8Encoding]::new($false))
    $taskRaw.AutoFlush=$true;$taskEvents.AutoFlush=$true
    $taskSerial.Open();$taskSerial.Write("stty -echo`r");Start-Sleep -Milliseconds 180
    $taskRaw.Write($taskSerial.ReadExisting())
    if (-not (Test-DemoViews)) {throw 'Video lost before execution'}
    $command='PYTHONPATH=/run/media/mmcblk0p2/piying/servo-capture-20261008-r4/integrations/calibration python3 -u /tmp/person_demo_once_20261011_a.py '+$BoardPlan+' --execute-attended-demo; echo DEMO_COMPLETE:$?; stty echo'
    $taskSerial.Write($command+"`r");$taskStarted=$true
    $taskDeadline=[DateTime]::UtcNow.AddSeconds(95);$lastLease=[DateTime]::MinValue;$pending=''
    while ([DateTime]::UtcNow -lt $taskDeadline) {
        if (-not $taskOff -and -not (Test-DemoViews) -and -not $taskInterrupted) {
            $taskReason='Camera guard or local stop request';$taskSerial.Write([string][char]3)
            $taskInterrupted=$true;$taskDeadline=[DateTime]::UtcNow.AddSeconds(5)
        }
        if (-not $taskOff -and -not $taskInterrupted -and ([DateTime]::UtcNow-$lastLease).TotalMilliseconds -ge 200) {
            $taskSerial.Write(": # PERSON_DEMO_LEASE`n");$lastLease=[DateTime]::UtcNow
        }
        $chunk=$taskSerial.ReadExisting()
        if ($chunk) {
            $taskRaw.Write($chunk);$pending+=$chunk
            while ($pending.Contains("`n")) {
                $cut=$pending.IndexOf("`n");$line=$pending.Substring(0,$cut).Trim();$pending=$pending.Substring($cut+1)
                if ($line.StartsWith('{"event":')) {
                    $event=$line|ConvertFrom-Json
                    $event|Add-Member -NotePropertyName host_unix_ms -NotePropertyValue ([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds())
                    $taskEvents.WriteLine(($event|ConvertTo-Json -Depth 12 -Compress))
                    if ($event.event -eq 'outputs_off') {
                        $taskOff=($event.state.enabled_mask -eq 0 -and -not $event.state.armed -and -not $event.state.pending)
                    }
                    if ($event.event -ne 'demo_step') {Write-Output $line}
                }
                if ($line -match '^DEMO_COMPLETE:(\d+)$') {
                    $taskComplete=($Matches[1] -eq '0');$taskDeadline=[DateTime]::MinValue
                }
            }
        }
        Start-Sleep -Milliseconds 25
    }
    if (-not $taskOff -or -not $taskComplete -or $taskInterrupted) {throw 'Demo incomplete; no retry; inspect evidence'}
    Write-Output 'DEMO_COMPLETE_ALL_OUTPUTS_OFF'
} finally {
    if ($taskSerial.IsOpen) {
        if ($taskStarted -and -not $taskOff) {$taskSerial.Write([string][char]3);Start-Sleep -Milliseconds 300}
        $taskSerial.Close()
    }
    $taskSerial.Dispose()
    if ($taskRaw) {$taskRaw.Dispose()};if ($taskEvents) {$taskEvents.Dispose()}
    if (Test-Path -LiteralPath $OutputDirectory) {
        [IO.File]::WriteAllText((Join-Path $OutputDirectory 'finish.request'),'finish')
        @{completed=$taskComplete;outputs_off_confirmed=$taskOff;interrupted=$taskInterrupted;reason=$taskReason}|
            ConvertTo-Json | Set-Content -LiteralPath (Join-Path $OutputDirectory 'capture_result.json') -Encoding utf8
    }
    $taskCapture.WaitForExit(3000)|Out-Null
}
