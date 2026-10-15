param([string]$PortName='COM3')
$ErrorActionPreference='Stop'
$taskProject=Split-Path -Parent $PSScriptRoot
$taskSources=Join-Path $taskProject 'integrations\calibration'
$taskPayload=@{}
foreach ($taskName in @('attended_center_console.py')) {
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
allowed={'attended_center_console.py'}
assert set(data)==allowed
root=pathlib.Path('/run/media/mmcblk0p2/piying/servo-capture-20261008-r4/integrations/calibration')
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
Write-Output 'Attended-center service files installed and syntax checked. No service or motor started.'
