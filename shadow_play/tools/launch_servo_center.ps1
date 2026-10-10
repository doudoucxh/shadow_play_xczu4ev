$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$runtimePython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$runtimePythonW = Join-Path (Split-Path -Parent $runtimePython) 'pythonw.exe'
$serialDeps = Join-Path $taskRoot '.review_work\servo_capture_20261008\python-deps'
$env:PYTHONPATH = $serialDeps
if (-not (Test-Path -LiteralPath $runtimePythonW)) { throw 'Python runtime missing. Ask to update the launcher path.' }
& $runtimePython -c 'import tkinter, serial'
if ($LASTEXITCODE -ne 0) { throw 'tkinter or pyserial unavailable.' }
$guiScript = Join-Path $PSScriptRoot 'servo_manual_gui.py'
Start-Process -FilePath $runtimePythonW -ArgumentList @('"' + $guiScript + '"') -WorkingDirectory $taskRoot -WindowStyle Hidden
