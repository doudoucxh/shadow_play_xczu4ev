param([string]$Source = "$PSScriptRoot\shadow-video-init", [string]$Target = '/tmp/shadow-video-init-candidate')
$ErrorActionPreference='Stop'
if($Target -notmatch '^/tmp/[A-Za-z0-9_.-]+$'){throw 'Target must be a simple /tmp file'}
$raw=[IO.File]::ReadAllBytes((Resolve-Path -LiteralPath $Source))
$stream=[IO.MemoryStream]::new()
$zip=[IO.Compression.GZipStream]::new($stream,[IO.Compression.CompressionMode]::Compress,$true)
$zip.Write($raw,0,$raw.Length);$zip.Dispose()
$b64=[Convert]::ToBase64String($stream.ToArray());$stream.Dispose()
$hash=(Get-FileHash -Algorithm SHA256 -LiteralPath $Source).Hash.ToLowerInvariant()
$port=[IO.Ports.SerialPort]::new('COM3',115200,[IO.Ports.Parity]::None,8,[IO.Ports.StopBits]::One)
$port.WriteTimeout=30000
function Read-Serial([int]$Milliseconds){
    $deadline=[DateTime]::UtcNow.AddMilliseconds($Milliseconds)
    while([DateTime]::UtcNow -lt $deadline){[Console]::Write($port.ReadExisting());Start-Sleep -Milliseconds 40}
}
try{
    $port.Open();Read-Serial 200
    $port.Write("stty -echo`r");Read-Serial 300
    $port.Write("python3 -c `"import sys,base64,gzip,hashlib,os;data=gzip.decompress(base64.b64decode(sys.stdin.read()));assert hashlib.sha256(data).hexdigest()=='$hash';open('$Target','wb').write(data);os.chmod('$Target',0o755);print('TRANSFER_OK $hash')`" <<'__VIDEO_PAYLOAD__'`r")
    for($i=0;$i -lt $b64.Length;$i+=512){
        $port.Write($b64.Substring($i,[Math]::Min(512,$b64.Length-$i))+"`r")
        Start-Sleep -Milliseconds 60
    }
    $port.Write("__VIDEO_PAYLOAD__`r");Read-Serial 2000
} finally {
    if($port.IsOpen){$port.Write("stty echo`r");Read-Serial 400;$port.Close()}
    $port.Dispose()
}
