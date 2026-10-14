param([Parameter(Mandatory=$true)][string]$OutputDirectory,
      [Parameter(Mandatory=$true)][string]$BoardPlan,
      [string]$PortName='COM3',
      [switch]$AttendedUnchangedContinuation,
      [switch]$AttendedLinkageComparison,
      [switch]$AttendedTigerCentering,
      [switch]$AttendedFixedChoreography,
      [switch]$WithTigerAudioSegment,
      [string]$HostPlan)
$ErrorActionPreference='Stop'
if (@(@($AttendedUnchangedContinuation,$AttendedLinkageComparison,$AttendedTigerCentering,$AttendedFixedChoreography) | Where-Object {$_}).Count -gt 1) {throw 'Choose one explicit attended mode'}
if ($AttendedUnchangedContinuation -or $AttendedLinkageComparison -or $AttendedTigerCentering -or $AttendedFixedChoreography) {
    $taskPlanPattern=if ($AttendedFixedChoreography) {'^/tmp/puppet_choreography_[a-z0-9_]+\.json$'} elseif ($AttendedTigerCentering) {'^/tmp/tiger_center_[a-z0-9_]+\.json$'} else {'^/tmp/person_visible_[a-z0-9_]+\.json$'}
    if ($BoardPlan -notmatch $taskPlanPattern) {throw 'Attended plan path required'}
    if (-not $HostPlan -or -not (Test-Path -LiteralPath $HostPlan -PathType Leaf)) {throw 'Local reviewed plan required'}
    $taskReviewedPlan=Get-Content -LiteralPath $HostPlan -Raw | ConvertFrom-Json
    if ($taskReviewedPlan.profile -eq 'person-body-double-smash-v3') {throw 'BE route withdrawn after stage 7 folded the puppet. Preserve the stop; no replay or automatic reverse.'}
    $taskPlanHash=(Get-FileHash -LiteralPath $HostPlan -Algorithm SHA256).Hash.ToLowerInvariant()
    $taskApproval=if ($AttendedFixedChoreography) {'attended-fixed-puppet-choreography-20261012'} elseif ($AttendedTigerCentering) {'attended-loaded-tiger-centering-20261012'} elseif ($AttendedLinkageComparison) {'attended-person-linkage-comparison-20261012'} else {'attended-unchanged-person-continuation-20261012'}
    if ($taskReviewedPlan.approval -ne $taskApproval) {throw 'Wrong continuation approval'}
    if ($WithTigerAudioSegment -and (-not $AttendedFixedChoreography -or $taskReviewedPlan.profile -ne 'tiger-operator-low-rear-fast')) {throw 'Audio segment supports only the attended FAST tiger route'}
} elseif ($BoardPlan -notmatch '^/tmp/person_recovery_[a-z0-9_]+\.json$') {throw 'Session plan path required'}
if ($WithTigerAudioSegment -and -not $AttendedFixedChoreography) {throw 'Audio segment requires attended fixed choreography'}
if (Test-Path -LiteralPath $OutputDirectory) {throw 'Use a new private session directory; no retry'}
$taskPython=Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$taskGuard=Join-Path $PSScriptRoot 'person_demo_camera_guard.py'
$taskCapture=Start-Process -FilePath $taskPython -ArgumentList @($taskGuard,$OutputDirectory,'--seconds','1000') -WindowStyle Hidden -PassThru
$taskSerial=[IO.Ports.SerialPort]::new($PortName,115200,[IO.Ports.Parity]::None,8,[IO.Ports.StopBits]::One)
$taskSerial.DtrEnable=$false;$taskSerial.RtsEnable=$false;$taskSerial.WriteTimeout=500
$taskOff=$false;$taskStarted=$false;$taskInterrupted=$false;$taskReason=$null
$taskRaw=$null;$taskEvents=$null;$taskSeen=@{}
function Test-RecoveryViews {
    if ($taskCapture.HasExited -or (Test-Path -LiteralPath (Join-Path $OutputDirectory 'guard.error'))) {return $false}
    $taskLeaseDirectory=Join-Path $OutputDirectory 'leases'
    $leaseFile=Get-ChildItem -LiteralPath $taskLeaseDirectory -Filter 'lease-*.json' -ErrorAction SilentlyContinue | Sort-Object Name | Select-Object -Last 1
    if (-not $leaseFile) {return $false}
    try {
        $stream=[IO.File]::Open($leaseFile.FullName,[IO.FileMode]::Open,[IO.FileAccess]::Read,([IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete))
        try {$reader=[IO.StreamReader]::new($stream);try {$value=$reader.ReadToEnd()|ConvertFrom-Json} finally {$reader.Dispose()}} finally {$stream.Dispose()}
        $age=[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()-[long]$value.unix_ms
        return ($age -ge 0 -and $age -lt 800)
    } catch {return $false}
}
try {
    $readyUntil=[DateTime]::UtcNow.AddSeconds(5)
    while (-not (Test-RecoveryViews) -and [DateTime]::UtcNow -lt $readyUntil) {Start-Sleep -Milliseconds 80}
    if (-not (Test-RecoveryViews)) {throw 'Two advancing camera streams not ready; no motion sent'}
    $taskRaw=[IO.StreamWriter]::new((Join-Path $OutputDirectory 'board.log'),$false,[Text.UTF8Encoding]::new($false))
    $taskEvents=[IO.StreamWriter]::new((Join-Path $OutputDirectory 'events.jsonl'),$false,[Text.UTF8Encoding]::new($false))
    $taskRaw.AutoFlush=$true;$taskEvents.AutoFlush=$true
    $taskSerial.Open();$taskSerial.Write("stty -echo`r");Start-Sleep -Milliseconds 180
    $taskRaw.Write($taskSerial.ReadExisting())
    if (-not (Test-RecoveryViews)) {throw 'Video lost before execution'}
    if ($AttendedUnchangedContinuation -or $AttendedLinkageComparison -or $AttendedTigerCentering -or $AttendedFixedChoreography) {
        $taskReviewAge=[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()-[long]$taskReviewedPlan.reviewed_at_unix_ms
        if ($taskReviewAge -lt 0 -or $taskReviewAge -ge 120000 -or (Get-FileHash -LiteralPath $HostPlan -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskPlanHash) {throw 'Physical comparison receipt expired or changed; no motion sent'}
        if ($AttendedFixedChoreography) {
            $taskActor=if ($taskReviewedPlan.profile -eq 'tiger-operator-low-rear-fast') {'/tmp/tiger_leap_session_20261014_r12.py'} elseif ($taskReviewedPlan.profile -eq 'tiger-operator-stretch-timeout-continuation') {'/tmp/tiger_leap_session_20261014_r11.py'} elseif ($taskReviewedPlan.profile -eq 'tiger-operator-low-rear-stretch') {'/tmp/tiger_leap_session_20261014_r11.py'} elseif ($taskReviewedPlan.profile -eq 'tiger-operator-up-left-leap') {'/tmp/tiger_leap_session_20261014_r9.py'} elseif ($taskReviewedPlan.profile -eq 'tiger-operator-screen-leap-bite') {'/tmp/tiger_leap_session_20261014_r8.py'} elseif ($taskReviewedPlan.profile -eq 'tiger-operator-screen-approach') {'/tmp/tiger_leap_session_20261014_r7.py'} elseif ($taskReviewedPlan.profile -eq 'tiger-operator-head-lower-ten-left') {'/tmp/tiger_leap_session_20261014_r6.py'} elseif ($taskReviewedPlan.profile -eq 'tiger-operator-head-lower-five') {'/tmp/tiger_leap_session_20261014_r5.py'} elseif ($taskReviewedPlan.profile -eq 'tiger-operator-head-lower-at-tree') {'/tmp/tiger_leap_session_20261014_r4.py'} elseif ($taskReviewedPlan.profile -eq 'tiger-operator-tree-position') {'/tmp/tiger_leap_session_20261014_r3.py'} elseif ($taskReviewedPlan.profile -eq 'tiger-operator-staggered-right-start') {'/tmp/tiger_leap_session_20261014_r2.py'} elseif ($taskReviewedPlan.profile -eq 'tiger-operator-leap-bite') {'/tmp/tiger_leap_session_20261014_r1.py'} elseif ($taskReviewedPlan.profile -eq 'person-operator-tiger-directed-combo') {'/tmp/hand_crossing_session_20261014_r36.py'} elseif ($taskReviewedPlan.profile -eq 'person-operator-head-direction-probe') {'/tmp/hand_crossing_session_20261014_r35.py'} elseif ($taskReviewedPlan.profile -eq 'person-operator-body-guard-combo') {'/tmp/hand_crossing_session_20261014_r34.py'} elseif ($taskReviewedPlan.profile -in @('person-tiger-duet','person-tiger-duet-bold')) {'/tmp/puppet_duet_session_20261012_r2.py'} elseif ($taskReviewedPlan.profile -in @('person-overhead-high280-yaw80-probe','person-overhead-high280-yaw160-probe','person-overhead-arc-entry-probe','person-overhead-operator-arc-trial','person-overhead-operator-low-arc-trial','person-overhead-operator-balanced-arc-trial','person-overhead-operator-jump-slow-trial','person-overhead-operator-return-arc-trial','person-overhead-operator-cross-entry-trial','person-overhead-operator-double-punch-trial','person-overhead-operator-punch-hold-trial','person-overhead-operator-punch-level-trial','person-overhead-operator-punch-extend-trial','person-operator-alternating-punch-combo','person-operator-alternating-guard-combo')) {'/tmp/hand_crossing_session_20261014_r33.py'} elseif ($taskReviewedPlan.profile -eq 'person-overhead-body-clearance-probe') {'/tmp/hand_crossing_session_20261014_r33.py'} elseif ($taskReviewedPlan.profile -eq 'person-overhead-lift-280-probe') {'/tmp/hand_crossing_session_20261014_r33.py'} elseif ($taskReviewedPlan.profile -in @('person-overhead-map-positive','person-overhead-map-negative','person-overhead-lift-clearance','person-overhead-high-map-positive','person-overhead-high-map-negative','person-script-hand-b-strike-probe','person-script-double-hit-probe','person-script-double-drop-sync-probe','person-script-hand-b-local-yaw-probe','person-script-hand-b-inward-80-probe','person-script-hand-b-inward-fold-probe','person-script-hand-a-local-yaw-probe','person-script-hand-a-inward-80-probe','person-reference-guard-counter-probe')) {'/tmp/hand_crossing_session_20261014_r33.py'} else {'/tmp/puppet_choreography_session_20261012_r5.py'}
            if ($WithTigerAudioSegment) {$taskActor='/tmp/tiger_audio_segment_20261014.py'}
            if ($taskReviewedPlan.profile -eq 'story-audio-v1') {$taskActor='/tmp/story_audio_session_20261014.py'}
            if ($taskReviewedPlan.profile -eq 'tiger-height-aw-v1') {$taskActor='/tmp/tiger_height_trial_20261014_r3.py'}
            if ($taskReviewedPlan.profile -eq 'tiger-shadow-roar-v1') {$taskActor='/tmp/tiger_shadow_roar_20261014.py'}
            if ($taskReviewedPlan.profile -eq 'person-body-double-smash-v1') {$taskActor='/tmp/person_variety_trial_20261014.py'}
            if ($taskReviewedPlan.profile -eq 'person-body-double-smash-v2') {$taskActor='/tmp/person_variety_trial_20261014_r2.py'}
            if ($taskReviewedPlan.profile -eq 'person-body-double-smash-v3') {$taskActor='/tmp/person_variety_trial_20261014_r3.py'}
            if ($taskReviewedPlan.profile -eq 'person-be-recovery-v1') {$taskActor='/tmp/person_be_recovery_20261014.py'}
            if ($taskReviewedPlan.profile -eq 'person-left-clearance-v1') {$taskActor='/tmp/person_left_clearance_20261014.py'}
            $command='PYTHONPATH=/tmp:/run/media/mmcblk0p2/piying/servo-capture-20261008-r4/integrations/calibration python3 -u '+$taskActor+' '+$BoardPlan+' --expected-plan-sha256 '+$taskPlanHash+' --execute-attended-fixed-choreography; echo RECOVERY_COMPLETE:$?; stty echo'
        } elseif ($AttendedTigerCentering) {
            $command='PYTHONPATH=/tmp:/run/media/mmcblk0p2/piying/servo-capture-20261008-r4/integrations/calibration python3 -u /tmp/tiger_center_session_20261012_r2.py '+$BoardPlan+' --expected-plan-sha256 '+$taskPlanHash+' --execute-attended-loaded-centering; echo RECOVERY_COMPLETE:$?; stty echo'
        } elseif ($AttendedLinkageComparison) {
            $command='PYTHONPATH=/tmp:/run/media/mmcblk0p2/piying/servo-capture-20261008-r4/integrations/calibration python3 -u /tmp/person_linkage_session_20261012_r15.py '+$BoardPlan+' --expected-plan-sha256 '+$taskPlanHash+' --execute-attended-linkage-comparison; echo RECOVERY_COMPLETE:$?; stty echo'
        } else {
            $command='PYTHONPATH=/tmp:/run/media/mmcblk0p2/piying/servo-capture-20261008-r4/integrations/calibration python3 -u /tmp/person_visible_motion_session_20261012_r4.py '+$BoardPlan+' --expected-plan-sha256 '+$taskPlanHash+' --execute-attended-unchanged-continuation; echo RECOVERY_COMPLETE:$?; stty echo'
        }
    } else {
        $command='PYTHONPATH=/run/media/mmcblk0p2/piying/servo-capture-20261008-r4/integrations/calibration python3 -u /tmp/person_recovery_session_20261012.py '+$BoardPlan+' --execute-released-person-recovery; echo RECOVERY_COMPLETE:$?; stty echo'
    }
    $taskSerial.Write($command+"`r");$taskStarted=$true
    $taskDeadline=[DateTime]::UtcNow.AddSeconds(915);$lastLease=[DateTime]::MinValue;$pending=''
    while ([DateTime]::UtcNow -lt $taskDeadline) {
        if (-not $taskOff -and -not $taskInterrupted) {
            if (Test-Path -LiteralPath (Join-Path $OutputDirectory 'stop.request')) {
                $taskReason='Operator emergency stop';$taskSerial.Write([string][char]3)
                $taskInterrupted=$true;$taskDeadline=[DateTime]::UtcNow.AddSeconds(5)
            } elseif (-not (Test-RecoveryViews)) {
                $taskReason='Video unavailable; frame stop requested';$taskSerial.Write(": # PERSON_RECOVERY_VIDEO_STOP`n")
                $taskInterrupted=$true;$taskDeadline=[DateTime]::UtcNow.AddSeconds(5)
            }
        }
        if (-not $taskOff -and -not $taskInterrupted) {
            if (([DateTime]::UtcNow-$lastLease).TotalMilliseconds -ge 200) {
                $taskSerial.Write(": # PERSON_RECOVERY_LEASE`n");$lastLease=[DateTime]::UtcNow
            }
            foreach ($file in @(Get-ChildItem -LiteralPath $OutputDirectory -Filter 'request-*.json' | Sort-Object Name)) {
                if ($taskSeen.ContainsKey($file.Name)) {continue}
                $request=Get-Content -LiteralPath $file.FullName -Raw|ConvertFrom-Json
                if ($request.action -notmatch '^(reconnected|probe_[1-6]|review_[1-6]|demo|finish)$' -or
                    $request.sequence -notmatch '^\d{1,10}$' -or [decimal]$request.sequence -ge 4294967296) {throw 'Invalid session action'}
                $taskSeen[$file.Name]=$true
                $taskSerial.Write(": # PERSON_RECOVERY_ACTION $($request.action) $($request.sequence)`n")
            }
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
                    if ($event.event -eq 'outputs_off') {$taskOff=($event.state.enabled_mask -eq 0 -and -not $event.state.armed -and -not $event.state.pending)}
                    if ($event.event -notin @('probe_step','reference_step','support_step','hold_alive')) {Write-Output $line}
                }
                if ($line -match '^RECOVERY_COMPLETE:(\d+)$') {$taskDeadline=[DateTime]::MinValue}
            }
        }
        Start-Sleep -Milliseconds 25
    }
    if (-not $taskOff) {throw 'Session ended without confirmed OFF; inspect, do not retry'}
} finally {
    if ($taskSerial.IsOpen) {
        if ($taskStarted -and -not $taskOff) {$taskSerial.Write([string][char]3);Start-Sleep -Milliseconds 300}
        $taskSerial.Close()
    }
    $taskSerial.Dispose()
    if ($taskRaw) {$taskRaw.Dispose()};if ($taskEvents) {$taskEvents.Dispose()}
    if (Test-Path -LiteralPath $OutputDirectory) {
        [IO.File]::WriteAllText((Join-Path $OutputDirectory 'finish.request'),'finish')
        @{outputs_off_confirmed=$taskOff;interrupted=$taskInterrupted;reason=$taskReason}|ConvertTo-Json|
            Set-Content -LiteralPath (Join-Path $OutputDirectory 'capture_result.json') -Encoding utf8
    }
    $taskCapture.WaitForExit(3000)|Out-Null
}
