param([switch]$SmokeTest)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$runtimePython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$runtimePythonW = Join-Path (Split-Path -Parent $runtimePython) 'pythonw.exe'
$serialDeps = Join-Path $taskRoot '.review_work\servo_capture_20261008\python-deps'
if ($env:PYTHONPATH) { $env:PYTHONPATH = $serialDeps + [IO.Path]::PathSeparator + $env:PYTHONPATH }
else { $env:PYTHONPATH = $serialDeps }
if (-not (Test-Path -LiteralPath $runtimePythonW)) { throw 'Python runtime missing. Ask to update the launcher path.' }
& $runtimePython -c 'import tkinter, serial'
if ($LASTEXITCODE -ne 0) { throw 'tkinter or pyserial unavailable.' }
$guiScript = Join-Path $PSScriptRoot 'attended_angle_gui.py'
if ($SmokeTest) {
    & $runtimePython $guiScript --smoke-test
    if ($LASTEXITCODE -ne 0) { throw 'Attended center panel smoke test failed.' }
} else {
    Start-Process -FilePath $runtimePythonW -ArgumentList @('"' + $guiScript + '"') -WorkingDirectory $taskRoot -WindowStyle Hidden
}
