param([switch]$SmokeTest, [string]$Profile)
$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$taskPython=Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$taskPythonW=Join-Path (Split-Path -Parent $taskPython) 'pythonw.exe'
$taskDeps=Join-Path $taskRoot '.review_work\servo_capture_20261008\python-deps'
if($env:PYTHONPATH){$env:PYTHONPATH=$taskRoot+[IO.Path]::PathSeparator+$taskDeps+[IO.Path]::PathSeparator+$env:PYTHONPATH}else{$env:PYTHONPATH=$taskRoot+[IO.Path]::PathSeparator+$taskDeps}
$taskTcl=Join-Path (Split-Path -Parent $taskPython) 'tcl\tcl8.6'
$taskTk=Join-Path (Split-Path -Parent $taskPython) 'tcl\tk8.6'
if(Test-Path -LiteralPath (Join-Path $taskTcl 'init.tcl')){$env:TCL_LIBRARY=$taskTcl;$env:TK_LIBRARY=$taskTk}
& $taskPython -c 'import tkinter, serial'
if($LASTEXITCODE -ne 0){throw 'Python tkinter/pyserial unavailable'}
$taskArgs=@('-m','shadow_play.bus_servo.gui')
if($Profile){$taskArgs+=@('--profile',('"'+(Resolve-Path -LiteralPath $Profile).Path+'"'))}
if($SmokeTest){
    & $taskPython -m shadow_play.bus_servo.gui --smoke-test
    if($LASTEXITCODE -ne 0){throw 'Bus-servo GUI smoke test failed'}
}else{
    Start-Process -FilePath $taskPythonW -ArgumentList $taskArgs -WorkingDirectory $taskRoot -WindowStyle Hidden
}
