param([string]$PortName='COM3',[switch]$FirstEdgeOnly,[switch]$ContinuationOnly,[switch]$HeightProbeOnly,[switch]$ReplayOnly,[switch]$HeadProbeOnly)
$ErrorActionPreference='Stop'
$taskProject=Split-Path -Parent $PSScriptRoot
$taskSources=Join-Path $taskProject 'integrations\calibration'
$taskPayload=@{}
if (@(@($FirstEdgeOnly,$ContinuationOnly,$HeightProbeOnly,$ReplayOnly,$HeadProbeOnly) | Where-Object {$_}).Count -gt 1) {throw 'Choose one installation scope'}
$taskNames=if ($ContinuationOnly) {@('story_midpoint_continue.py','story_audio_session_v3.py')} elseif ($FirstEdgeOnly) {@('story_midpoint_first_edge.py')} else {@('story_midpoint_continue.py','story_midpoint_first_edge.py','story_midpoint_session.py','story_audio_session_v3.py','story_motion_v3_candidate.py','duel_interaction_trial.py','puppet_choreography_session.py','person_recovery_session.py','tiger_center_session.py','tiger_audio_segment.py')}
if ($HeightProbeOnly) {$taskNames=@('tiger_roll_probe.py')}
if ($ReplayOnly) {$taskNames=@('story_replay_from_height.py')}
if ($HeadProbeOnly) {$taskNames=@('person_head_contact_probe.py')}
foreach ($taskName in $taskNames) {
    $taskPayload[$taskName]=[Convert]::ToBase64String([IO.File]::ReadAllBytes((Join-Path $taskSources $taskName)))
}
$taskBytes=[Text.Encoding]::UTF8.GetBytes(($taskPayload|ConvertTo-Json -Compress))
$taskMemory=[IO.MemoryStream]::new()
$taskGzip=[IO.Compression.GZipStream]::new($taskMemory,[IO.Compression.CompressionMode]::Compress,$true)
$taskGzip.Write($taskBytes,0,$taskBytes.Length);$taskGzip.Dispose()
$taskEncoded=[Convert]::ToBase64String($taskMemory.ToArray());$taskMemory.Dispose()
$taskId=[Guid]::NewGuid().ToString('N')
$taskLocal=Join-Path $taskProject ('logs\story_start_install\'+$taskId)
New-Item -ItemType Directory -Path $taskLocal -Force | Out-Null
$taskRemote='/tmp/piying-story-upload-'+$taskId+'.txt'
$taskStep=0
function Send-InstallCommand([string]$Text) {
    $taskCommandFile=Join-Path $taskLocal ('command-'+$script:taskStep+'.sh')
    [IO.File]::WriteAllText($taskCommandFile,$Text,[Text.UTF8Encoding]::new($false))
    & (Join-Path $PSScriptRoot 'board_serial.ps1') -PortName $PortName -CommandFile $taskCommandFile -Quiet -TimeoutSeconds 8 -LogPath (Join-Path $taskLocal ('reply-'+$script:taskStep+'.log'))
    $script:taskStep++
}
# File transfer and syntax compilation only. No service, MMIO or motion is started.
Send-InstallCommand ('python3 -c "open(''{0}'',''x'').close()"' -f $taskRemote)
for ($taskOffset=0;$taskOffset -lt $taskEncoded.Length;$taskOffset+=1500) {
    $taskChunk=$taskEncoded.Substring($taskOffset,[Math]::Min(1500,$taskEncoded.Length-$taskOffset))
    Send-InstallCommand ('python3 -c "open(''{0}'',''a'').write(''{1}'')"' -f $taskRemote,$taskChunk)
}
$taskFinish=@'
python3 - <<'PY'
import base64,gzip,json,pathlib,py_compile
src=pathlib.Path('UPLOAD')
data=json.loads(gzip.decompress(base64.b64decode(src.read_bytes(),validate=True)))
full={'story_midpoint_continue.py','story_midpoint_first_edge.py','story_midpoint_session.py','story_audio_session_v3.py','story_motion_v3_candidate.py','duel_interaction_trial.py','puppet_choreography_session.py','person_recovery_session.py','tiger_center_session.py','tiger_audio_segment.py'}
assert set(data) in (full,{'story_midpoint_first_edge.py'},{'story_midpoint_continue.py','story_audio_session_v3.py'},{'tiger_roll_probe.py'},{'story_replay_from_height.py'},{'person_head_contact_probe.py'})
allowed=set(data)
root=pathlib.Path('/tmp/story-midpoint-20261015')
root.mkdir(exist_ok=True)
for name in sorted(allowed):
    path=root/name
    path.write_bytes(base64.b64decode(data[name],validate=True))
    py_compile.compile(str(path),doraise=True)
src.unlink()
print('INSTALLED_NO_MOTOR_COMMANDS')
PY
'@
Send-InstallCommand ($taskFinish.Replace('UPLOAD',$taskRemote))
Write-Output 'Midpoint rehearsal service files installed and syntax checked. No service or motor started.'
