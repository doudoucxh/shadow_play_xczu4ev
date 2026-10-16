param(
    [Parameter(Mandatory=$true)][string]$Source,
    [Parameter(Mandatory=$true)][string]$Target,
    [string]$PortName = 'COM3',
    [int]$BaudRate = 115200
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'board_shell_guard.ps1')
if ($Target -notmatch '^/tmp/[A-Za-z0-9_.-]+$') { throw 'Target must be a simple /tmp filename.' }
$raw = [IO.File]::ReadAllBytes((Resolve-Path -LiteralPath $Source))
$hash = (Get-FileHash -LiteralPath $Source -Algorithm SHA256).Hash.ToLowerInvariant()
$stream = [IO.MemoryStream]::new()
$gzip = [IO.Compression.GZipStream]::new($stream,[IO.Compression.CompressionMode]::Compress,$true)
$gzip.Write($raw,0,$raw.Length)
$gzip.Dispose()
$payload = [Convert]::ToBase64String($stream.ToArray())
$stream.Dispose()
$chunks = [int][Math]::Ceiling($payload.Length / 1024.0)
$receiveLoop = "for i in range($chunks):\n line=sys.stdin.readline().strip().split(':',2)\n assert len(line)==3 and int(line[0])==i, 'chunk sequence mismatch'\n assert hashlib.sha256(line[2].encode('ascii')).hexdigest()==line[1], 'chunk checksum mismatch'\n parts.append(line[2])\n print('CHUNK_OK '+str(i),flush=True)"
$python = "import sys,base64,gzip,hashlib; print('TRANSFER_READY',flush=True); parts=[]; exec(" + "'" + $receiveLoop.Replace("'","\'") + "'); data=gzip.decompress(base64.b64decode(''.join(parts),validate=True)); assert hashlib.sha256(data).hexdigest()=='$hash'; f=open('$Target','xb'); f.write(data); f.close(); print('TRANSFER_OK $hash',flush=True)"
$serial = [IO.Ports.SerialPort]::new($PortName,$BaudRate,[IO.Ports.Parity]::None,8,[IO.Ports.StopBits]::One)
$serial.DtrEnable = $false
$serial.RtsEnable = $false
$serial.WriteTimeout = 15000
$captured = [Text.StringBuilder]::new()
$success = $false
$echoDisabled = $false
try {
    $serial.Open()
    Wait-BoardShell -Serial $serial
    $serial.Write("stty -echo`r")
    $echoDisabled = $true
    Start-Sleep -Milliseconds 200
    [void]$serial.ReadExisting()
    $serial.Write('python3 -u -c "' + $python + '"' + "`r")
    $deadline = [DateTime]::UtcNow.AddSeconds(8)
    while ($captured.ToString() -notmatch '(?m)^TRANSFER_READY\r?$') {
        [void]$captured.Append($serial.ReadExisting())
        if ([DateTime]::UtcNow -gt $deadline) { throw ('Receiver not ready: ' + $captured.ToString()) }
        Start-Sleep -Milliseconds 20
    }
    $nextReport = [DateTime]::UtcNow.AddSeconds(15)
    for ($i=0; $i -lt $payload.Length; $i+=1024) {
        $chunk = $payload.Substring($i,[Math]::Min(1024,$payload.Length-$i))
        $chunkNumber = [int]($i / 1024)
        $hasher = [Security.Cryptography.SHA256]::Create()
        try { $chunkHash = [BitConverter]::ToString($hasher.ComputeHash([Text.Encoding]::ASCII.GetBytes($chunk))).Replace('-','').ToLowerInvariant() }
        finally { $hasher.Dispose() }
        $serial.Write("${chunkNumber}:${chunkHash}:${chunk}`r")
        $chunkDeadline = [DateTime]::UtcNow.AddSeconds(10)
        while ($captured.ToString() -notmatch "(?m)^CHUNK_OK $chunkNumber\r?$") {
            [void]$captured.Append($serial.ReadExisting())
            if ([DateTime]::UtcNow -gt $chunkDeadline) { throw "No checksum acknowledgement for chunk $chunkNumber; transfer stopped." }
            Start-Sleep -Milliseconds 5
        }
        if ([DateTime]::UtcNow -ge $nextReport) {
            Write-Output ('Transfer {0}% ({1} / {2} encoded bytes)' -f [Math]::Floor(100*$i/$payload.Length),$i,$payload.Length)
            $nextReport = [DateTime]::UtcNow.AddSeconds(15)
        }
    }
    $deadline = [DateTime]::UtcNow.AddSeconds(30)
    while ($captured.ToString() -notmatch "(?m)^TRANSFER_OK $hash\r?$") {
        [void]$captured.Append($serial.ReadExisting())
        if ([DateTime]::UtcNow -gt $deadline) { throw ('Transfer did not verify: ' + $captured.ToString()) }
        Start-Sleep -Milliseconds 40
    }
    $success = $true
    Write-Output "TRANSFER_OK $hash ($($raw.Length) bytes) -> $Target"
} finally {
    if ($serial.IsOpen) {
        if ($echoDisabled) {
            if (-not $success) { $serial.Write([string][char]3); Start-Sleep -Milliseconds 200 }
            $serial.Write("stty echo`r")
            Start-Sleep -Milliseconds 200
        }
        $serial.Close()
    }
    $serial.Dispose()
}
