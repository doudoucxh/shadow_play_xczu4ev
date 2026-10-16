param(
    [string]$PortName = 'COM3',
    [int]$BaudRate = 115200,
    [string]$CommandFile,
    [int]$TimeoutSeconds = 30,
    [string]$LogPath,
    [switch]$Quiet
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'board_shell_guard.ps1')
$serial = [IO.Ports.SerialPort]::new($PortName, $BaudRate, [IO.Ports.Parity]::None, 8, [IO.Ports.StopBits]::One)
$serial.DtrEnable = $false
$serial.RtsEnable = $false
$serial.Encoding = [Text.Encoding]::UTF8
$serial.WriteTimeout = 5000
$captured = [Text.StringBuilder]::new()
$tag = [Guid]::NewGuid().ToString('N')
$echoDisabled = $false
try {
    $serial.Open()
    Start-Sleep -Milliseconds 200
    $initial = $serial.ReadExisting()
    if ($initial) { if (-not $Quiet) { [Console]::Write($initial) }; [void]$captured.Append($initial) }
    if ($CommandFile) {
        Wait-BoardShell -Serial $serial -Initial $initial
        $command = "export SYSTEMD_PAGER=cat PAGER=cat`n" + [IO.File]::ReadAllText((Resolve-Path -LiteralPath $CommandFile), [Text.Encoding]::UTF8).Replace("`r`n", "`n")
        $payload = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($command))
        $line = 'python3 -c "import base64,subprocess,sys; print(''__BOARD_BEGIN_TAG__'',flush=True); result=subprocess.call(base64.b64decode(''PAYLOAD'').decode(''utf-8''),shell=True); print(''__BOARD_END_TAG__:%d''%result,flush=True); sys.exit(result)"'
        $line = $line.Replace('TAG', $tag).Replace('PAYLOAD', $payload)
        if ($line.Length -gt 3800) { throw 'Command too long for a canonical serial terminal; split into smaller commands.' }
        $serial.Write("stty -echo`r")
        $echoDisabled = $true
        Start-Sleep -Milliseconds 200
        [void]$serial.ReadExisting()
        $serial.Write($line + "`r")
    } else {
        $serial.Write("`r")
    }
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    $finished = $false
    while ([DateTime]::UtcNow -lt $deadline) {
        $chunk = $serial.ReadExisting()
        if ($chunk) {
            if (-not $Quiet) { [Console]::Write($chunk) }
            [void]$captured.Append($chunk)
            if ($CommandFile -and $captured.ToString() -match "(?m)^__BOARD_END_${tag}__:(\d+)\r?$") {
                $returnCode = [int]$Matches[1]
                $finished = $true
                break
            }
        }
        Start-Sleep -Milliseconds 40
    }
    if ($CommandFile -and -not $finished) { throw 'No completion marker received; inspect serial output before retrying.' }
    if ($CommandFile -and $returnCode -ne 0) { throw "Board command exited with code $returnCode" }
} finally {
    if ($serial.IsOpen) {
        if ($echoDisabled) { $serial.Write("stty echo`r"); Start-Sleep -Milliseconds 200 }
        $serial.Close()
    }
    $serial.Dispose()
    if ($LogPath) { [IO.File]::WriteAllText($LogPath, $captured.ToString(), [Text.UTF8Encoding]::new($false)) }
}
