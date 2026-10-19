param(
    [Parameter(Mandatory=$true)][string]$Source,
    [Parameter(Mandatory=$true)][string]$Target,
    [string]$PortName='COM17',
    [ValidateSet(115200,460800,921600)][int]$FastBaud=921600,
    [string]$Receiver='/tmp/shadow-file-receiver-20261017-v2.py'
)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'board_shell_guard.ps1')
if($Target -notmatch '^/tmp/[A-Za-z0-9_-][A-Za-z0-9_.-]*$' -or $Receiver -notmatch '^/tmp/[A-Za-z0-9_-][A-Za-z0-9_.-]*\.py$'){throw 'Only simple /tmp paths accepted'}
$inputPath=(Resolve-Path -LiteralPath $Source).Path
$size=(Get-Item -LiteralPath $inputPath).Length
if($size -le 0 -or $size -gt 209715200){throw 'File must be 1..200 MiB'}
$hash=(Get-FileHash -LiteralPath $inputPath -Algorithm SHA256).Hash.ToLowerInvariant()
$s=[IO.Ports.SerialPort]::new($PortName,115200,[IO.Ports.Parity]::None,8,[IO.Ports.StopBits]::One)
$s.DtrEnable=$false;$s.RtsEnable=$false;$s.WriteTimeout=10000
$started=$false;$complete=$false;$inputStream=$null;$pending=''
function Await-Line([string]$pattern,[int]$seconds=12) {
    $deadline=[DateTime]::UtcNow.AddSeconds($seconds)
    while([DateTime]::UtcNow -lt $deadline){
        $script:pending += $s.ReadExisting()
        $match=[regex]::Match($script:pending,$pattern)
        if($match.Success){$script:lastMatch=$match;$script:pending=$script:pending.Substring($match.Index+$match.Length);return}
        if($script:pending.Length -gt 16384){throw 'Unexpected UART output'}
        Start-Sleep -Milliseconds 5
    }
    throw "UART timeout waiting for $pattern. Receiver output: $script:pending"
}
try {
    $s.Open();Wait-BoardShell -Serial $s
    $s.Write("stty -echo`r");Start-Sleep -Milliseconds 200;[void]$s.ReadExisting()
    $s.Write("python3 -u $Receiver $Target $size $hash --baud $FastBaud --resume`r")
    $started=$true
    Await-Line '(?m)^BINARY_READY ([0-9]+) ([a-f0-9]{64})\r?\n'
    $resume=[int64]$script:lastMatch.Groups[1].Value
    $prefixHash=$script:lastMatch.Groups[2].Value
    if($resume -gt $size -or ($resume -ne $size -and $resume%32768)){throw 'Invalid resume offset'}
    $inputStream=[IO.File]::OpenRead($inputPath)
    $prefixHasher=[Security.Cryptography.SHA256]::Create()
    try {
        $prefixBuffer=New-Object byte[] 32768;$remaining=$resume
        while($remaining -gt 0){$n=$inputStream.Read($prefixBuffer,0,[math]::Min($remaining,32768));if(!$n){throw 'Short source file'};[void]$prefixHasher.TransformBlock($prefixBuffer,0,$n,$prefixBuffer,0);$remaining-=$n}
        [void]$prefixHasher.TransformFinalBlock(@(),0,0)
        $actualPrefix=[BitConverter]::ToString($prefixHasher.Hash).Replace('-','').ToLowerInvariant()
        if($actualPrefix -ne $prefixHash){throw 'Partial prefix checksum mismatch'}
    }finally{$prefixHasher.Dispose()}
    $s.BaudRate=$FastBaud;Start-Sleep -Milliseconds 700
    $buffer=New-Object byte[] 32768
    $index=[int]($resume/32768);$sent=$resume;$lastReport=[DateTime]::UtcNow
    Write-Output "Verified resume prefix: $resume bytes"
    while(($count=$inputStream.Read($buffer,0,$buffer.Length)) -gt 0){
        $numberBytes=[BitConverter]::GetBytes([int]$index);[Array]::Reverse($numberBytes)
        $lengthBytes=[BitConverter]::GetBytes([int]$count);[Array]::Reverse($lengthBytes)
        $hasher=[Security.Cryptography.SHA256]::Create()
        try{$checksum=$hasher.ComputeHash($buffer,0,$count)}finally{$hasher.Dispose()}
        $s.Write($numberBytes,0,4);$s.Write($lengthBytes,0,4);$s.Write($checksum,0,32)
        for($part=0;$part -lt $count;$part+=4096){$s.Write($buffer,$part,[math]::Min(4096,$count-$part));Start-Sleep -Milliseconds 1}
        Await-Line "(?m)^ACK $index\r?\n"
        $index++;$sent+=$count
        if(([DateTime]::UtcNow-$lastReport).TotalSeconds -ge 15){Write-Output "Transfer $sent / $size bytes ($([math]::Floor(100*$sent/$size))%)";$lastReport=[DateTime]::UtcNow}
    }
    Await-Line "(?m)^FILE_OK $hash\r?\n"
    $complete=$true
    Write-Output "TRANSFER_OK $hash ($size bytes) -> $Target"
} finally {
    if($inputStream){$inputStream.Dispose()}
    if($s.IsOpen){
        # Receiver restores its saved termios after completion or 15 s idle.
        if($started){Start-Sleep -Milliseconds $(if($complete){800}else{17000})}
        $s.BaudRate=115200
        $s.Write("`r");Start-Sleep -Milliseconds 200
        if($complete){$s.Write("stty echo`r")}
        $s.Close()
    }
    $s.Dispose()
}
