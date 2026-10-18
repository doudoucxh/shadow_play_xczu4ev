param([string]$PortName='COM17')
$ErrorActionPreference='Stop'
$taskProject=Split-Path -Parent $PSScriptRoot
$taskPython=Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$taskId=[Guid]::NewGuid().ToString('N')
$taskLocal=Join-Path $taskProject ('logs\initial_pose_install\'+$taskId)
New-Item -ItemType Directory -Path $taskLocal -Force | Out-Null
$taskArchive=Join-Path $taskLocal 'service.tar.gz'
$taskBuilder=Join-Path $PSScriptRoot 'build_initial_pose_service.py'
& $taskPython $taskBuilder build $taskArchive
if($LASTEXITCODE -ne 0){throw 'Service bundle build failed'}
$taskHash=(Get-FileHash -LiteralPath $taskArchive -Algorithm SHA256).Hash.ToLowerInvariant()
$taskRemoteArchive='/tmp/initial-pose-'+$taskId+'.tar.gz'
$taskRemoteBuilder='/tmp/initial-pose-'+$taskId+'.py'
& (Join-Path $PSScriptRoot 'board_transfer.ps1') -PortName $PortName -Source $taskArchive -Target $taskRemoteArchive
& (Join-Path $PSScriptRoot 'board_transfer.ps1') -PortName $PortName -Source $taskBuilder -Target $taskRemoteBuilder
$taskCommand='python3 '+$taskRemoteBuilder+' install '+$taskRemoteArchive+' --sha256 '+$taskHash
$taskCommandPath=Join-Path $taskLocal 'install.sh'
[IO.File]::WriteAllText($taskCommandPath,$taskCommand,[Text.UTF8Encoding]::new($false))
& (Join-Path $PSScriptRoot 'board_serial.ps1') -PortName $PortName -CommandFile $taskCommandPath -LogPath (Join-Path $taskLocal 'install.log') -TimeoutSeconds 15
Write-Output 'Initial-angle service installed and syntax checked. No service or motion started.'
