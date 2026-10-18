param([string]$CameraIP = '192.168.31.250', [ValidateRange(10,86400)][int]$Seconds = 28800,
      [ValidateRange(1,15)][int]$FramesPerSecond = 15,
      [System.Management.Automation.PSCredential]$CameraCredential)
$ErrorActionPreference = 'Stop'
$exe = Join-Path $PSScriptRoot 'build\sony_liveview.exe'
if(-not (Test-Path -LiteralPath $exe)){ throw 'Run build.ps1 first.' }
$active = Get-Process -Name sony_liveview -ErrorAction SilentlyContinue
if($active){throw 'A live-view process is already running. Run stop_liveview.ps1 first.'}
if(Get-Process -Name Remote -ErrorAction SilentlyContinue){
    throw 'Close the Sony Imaging Edge Remote window first, then run this command again.'
}
$run = Join-Path $PSScriptRoot ('output\session-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
New-Item -ItemType Directory -Path $run -Force | Out-Null
if ($CameraCredential) {
    $userId = $CameraCredential.UserName
    $secret = $CameraCredential.Password.Copy()
} else {
    $userId = Read-Host 'Camera Access Authentication user name (not your Sony account)'
    $secret = Read-Host 'Camera Access Authentication password (input hidden)' -AsSecureString
}
$bstr = [IntPtr]::Zero
$proc = [Diagnostics.Process]::new()
$started = $false
try {
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
    $passwordText = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    if([string]::IsNullOrWhiteSpace($userId) -or [string]::IsNullOrEmpty($passwordText)){throw 'Credentials cannot be empty.'}
    if($userId.Contains("`n") -or $passwordText.Contains("`n")){throw 'Credentials cannot contain newlines.'}
    $proc.StartInfo.FileName = $exe
    $proc.StartInfo.WorkingDirectory = Split-Path $exe
    $proc.StartInfo.Arguments = 'live "' + $CameraIP + '" "' + $run + '" ' + $Seconds + ' ' + $FramesPerSecond
    $proc.StartInfo.UseShellExecute = $false
    $proc.StartInfo.CreateNoWindow = $true
    $proc.StartInfo.WindowStyle = [Diagnostics.ProcessWindowStyle]::Hidden
    $proc.StartInfo.RedirectStandardInput = $true
    $proc.StartInfo.RedirectStandardOutput = $true
    $proc.StartInfo.RedirectStandardError = $true
    if(-not $proc.Start()){throw 'Cannot start live-view helper.'}
    $started = $true
    $stdout = $proc.StandardOutput.ReadToEndAsync()
    $stderr = $proc.StandardError.ReadToEndAsync()
    $proc.StandardInput.WriteLine($userId)
    $proc.StandardInput.WriteLine($passwordText)
    $proc.StandardInput.Close()
    $passwordText = $null
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    $bstr = [IntPtr]::Zero
    $pointer = @{directory=$run;pid=$proc.Id;camera_ip=$CameraIP;started=(Get-Date).ToString('o');duration_seconds=$Seconds;fps=$FramesPerSecond}
    [IO.File]::WriteAllText((Join-Path $PSScriptRoot 'output\current.json'), ($pointer | ConvertTo-Json), [Text.UTF8Encoding]::new($false))
    Write-Host "Live view output: $run"
    Write-Host 'Keep this terminal open. To stop, run stop_liveview.ps1 in another terminal.'
    Write-Host ('Requested duration: ' + $Seconds + ' seconds; default is 8 hours.')
    $reported = $false
    $previousFrame = -1L
    $advancingSamples = 0
    while(-not $proc.WaitForExit(500)) {
        $statusPath = Join-Path $run 'status.json'
        if(-not $reported -and (Test-Path -LiteralPath $statusPath)){
            try { $state = Get-Content -LiteralPath $statusPath -Raw | ConvertFrom-Json } catch { continue }
            $ageMs = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() - [long]$state.updated_unix_ms
            if($state.state -eq 'streaming' -and $ageMs -ge -1000 -and $ageMs -le 2000){
                if([long]$state.frames -gt $previousFrame){$advancingSamples++}
                elseif([long]$state.frames -lt $previousFrame){$advancingSamples=0}
            } else {
                $advancingSamples = 0
            }
            $previousFrame = [long]$state.frames
            if($advancingSamples -ge 3){
                Write-Host ('LIVE VIEW READY: verified advancing frames, latest age ' + $ageMs + ' ms')
                $reported=$true
            }
        }
    }
    $stdoutText = $stdout.GetAwaiter().GetResult()
    $stderrText = $stderr.GetAwaiter().GetResult()
    [IO.File]::WriteAllText((Join-Path $run 'helper.log'), $stdoutText + $stderrText, [Text.UTF8Encoding]::new($false))
    Write-Host ($stdoutText + $stderrText)
    if($proc.ExitCode -ne 0){throw ('Live-view helper exited with code ' + $proc.ExitCode)}
} finally {
    if($bstr -ne [IntPtr]::Zero){[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)}
    $passwordText = $null
    if($secret){$secret.Dispose()}
    if($started -and -not $proc.HasExited){
        [IO.File]::WriteAllText((Join-Path $run 'stop.request'), 'stop')
        if(-not $proc.WaitForExit(10000)){$proc.Kill()}
    }
    $proc.Dispose()
}
