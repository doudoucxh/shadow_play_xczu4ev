param([switch]$SmokeTest, [string]$Profile, [switch]$AudioEditor, [switch]$PoseLibrary)
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
$taskModule=if($PoseLibrary){'shadow_play.bus_servo.pose_gui'}else{'shadow_play.bus_servo.gui'}
if($PoseLibrary -and $AudioEditor){throw 'Choose either PoseLibrary or AudioEditor'}
$taskArgs=@('-m',$taskModule)
if($AudioEditor){$taskArgs+='--av-editor'}
if($Profile){$taskArgs+=@('--profile',('"'+(Resolve-Path -LiteralPath $Profile).Path+'"'))}
if($SmokeTest){
    $taskSmokeArgs=@('--smoke-test')
    if($Profile){$taskSmokeArgs+=@('--profile',(Resolve-Path -LiteralPath $Profile).Path)}
    if($AudioEditor){$taskSmokeArgs+='--av-editor'}
    & $taskPython -m $taskModule @taskSmokeArgs
    if($LASTEXITCODE -ne 0){throw 'Bus-servo GUI smoke test failed'}
}else{
    Start-Process -FilePath $taskPythonW -ArgumentList $taskArgs -WorkingDirectory $taskRoot -WindowStyle Hidden
}
