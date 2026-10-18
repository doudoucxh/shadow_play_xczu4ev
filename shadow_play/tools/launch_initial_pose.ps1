param([switch]$SmokeTest)
$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$taskPython=Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$taskPythonW=Join-Path (Split-Path -Parent $taskPython) 'pythonw.exe'
$taskDeps=Join-Path $taskRoot '.review_work\servo_capture_20261008\python-deps'
if($env:PYTHONPATH){$env:PYTHONPATH=$taskDeps+[IO.Path]::PathSeparator+$env:PYTHONPATH}else{$env:PYTHONPATH=$taskDeps}
if(-not(Test-Path -LiteralPath $taskPythonW)){throw 'Bundled Python runtime unavailable'}
$taskTcl=Join-Path (Split-Path -Parent $taskPython) 'tcl\tcl8.6'
$taskTk=Join-Path (Split-Path -Parent $taskPython) 'tcl\tk8.6'
if(Test-Path -LiteralPath (Join-Path $taskTcl 'init.tcl')){$env:TCL_LIBRARY=$taskTcl;$env:TK_LIBRARY=$taskTk}
& $taskPython -c 'import tkinter, serial'
if($LASTEXITCODE -ne 0){throw 'tkinter or pyserial unavailable'}
$taskGui=Join-Path $PSScriptRoot 'initial_pose_gui.py'
if($SmokeTest){
    & $taskPython $taskGui --smoke-test
    if($LASTEXITCODE -ne 0){throw 'Initial-angle UI smoke test failed'}
}else{
    $taskProcess=Start-Process -FilePath $taskPythonW -ArgumentList @('"'+$taskGui+'"') -WorkingDirectory $taskRoot -WindowStyle Hidden -PassThru
    Write-Output ('INITIAL_POSE_WINDOW_STARTED PID='+$taskProcess.Id)
}
