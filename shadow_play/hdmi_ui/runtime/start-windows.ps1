$ErrorActionPreference = 'Stop'
$taskRuntime = Split-Path -Parent $MyInvocation.MyCommand.Path
$taskPort = 8765
$taskUrl = 'http://127.0.0.1:8765/'
$taskExpectedSha = (Get-FileHash -LiteralPath (Join-Path $taskRuntime 'web/index.html') -Algorithm SHA256).Hash
$taskPython = Get-Command python -ErrorAction SilentlyContinue
if (-not $taskPython) { $taskPython = Get-Command python3 -ErrorAction SilentlyContinue }
if (-not $taskPython) { throw 'Install Python 3, then run this script again.' }
$taskHealthy = $false
try { $taskHealth = Invoke-RestMethod ($taskUrl + 'health.json') -TimeoutSec 1; $taskHealthy = $taskHealth.app -eq 'shadow-theatre-hdmi' -and $taskHealth.ui_sha256 -eq $taskExpectedSha } catch {}
if (-not $taskHealthy) {
    Start-Process -FilePath $taskPython.Source -WindowStyle Hidden -ArgumentList @(('"' + (Join-Path $taskRuntime 'serve.py') + '"'), '--port', "$taskPort")
}
for ($taskTry = 0; $taskTry -lt 40; $taskTry++) {
    try { $taskHealth = Invoke-RestMethod ($taskUrl + 'health.json') -TimeoutSec 1; if ($taskHealth.app -eq 'shadow-theatre-hdmi' -and $taskHealth.ui_sha256 -eq $taskExpectedSha) { $taskHealthy = $true; break } } catch {}
    Start-Sleep -Milliseconds 100
}
if (-not $taskHealthy) { throw 'The matching UI did not start. Close the old UI and stop its server before retrying; port 8765 may be occupied.' }
$taskBrowsers = @("$env:ProgramFiles\Google\Chrome\Application\chrome.exe", "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe", "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe")
$taskBrowser = $taskBrowsers | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if ($taskBrowser) {
    Start-Process -FilePath $taskBrowser -ArgumentList @('--new-window', "--app=$taskUrl", '--window-size=1024,600', '--force-device-scale-factor=1')
} else { Start-Process $taskUrl }
Write-Host "UI: $taskUrl  (Use F11 for full screen if needed.)"
