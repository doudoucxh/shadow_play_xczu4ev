param([switch]$CheckOnly)
$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$taskPython=Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
if(-not(Test-Path -LiteralPath $taskPython)){throw 'Python runtime unavailable'}
$env:PYTHONUTF8='1'
$env:PYTHONIOENCODING='utf-8'
Push-Location -LiteralPath $taskRoot
try{
    & $taskPython (Join-Path $PSScriptRoot 'v20_full_preparation.py') --verify-only
    if($LASTEXITCODE -ne 0){throw 'V20 preparation integrity check failed'}
    if(-not $CheckOnly){
        # Interactive preview is opened only when this launcher is run by the user.
        Start-Process -FilePath (Join-Path $taskRoot 'shadow_play\planning\wusong_v20_full_20261019\preview.html')
    }
}finally{Pop-Location}
