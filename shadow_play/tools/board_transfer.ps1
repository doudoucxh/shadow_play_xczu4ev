param(
    [Parameter(Mandatory=$true)][string]$Source,
    [Parameter(Mandatory=$true)][string]$Target,
    [string]$PortName = 'COM3',
    [int]$BaudRate = 115200
)
$ErrorActionPreference = 'Stop'
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
$python = "import sys,base64,gzip,hashlib; print('TRANSFER_READY',flush=True); data=gzip.decompress(base64.b64decode(''.join(sys.stdin.readline().strip() for _ in range($chunks)),validate=True)); assert hashlib.sha256(data).hexdigest()=='$hash'; f=open('$Target','xb'); f.write(data); f.close(); print('TRANSFER_OK $hash',flush=True)"
$serial = [IO.Ports.SerialPort]::new($PortName,$BaudRate,[IO.Ports.Parity]::None,8,[IO.Ports.StopBits]::One)
$serial.DtrEnable = $false
$serial.RtsEnable = $false
$serial.WriteTimeout = 15000
$captured = [Text.StringBuilder]::new()
$success = $false
try {
    $serial.Open()
    $serial.Write("stty -echo`r")
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
        $serial.Write($payload.Substring($i,[Math]::Min(1024,$payload.Length-$i))+"`r")
        [void]$captured.Append($serial.ReadExisting())
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
        if (-not $success) { $serial.Write([string][char]3); Start-Sleep -Milliseconds 200 }
        $serial.Write("stty echo`r")
        Start-Sleep -Milliseconds 200
        $serial.Close()
    }
    $serial.Dispose()
}
