param(
    [string]$PortName='COM9',
    [string]$Username='petalinux',
    [Parameter(Mandatory=$true)][Security.SecureString]$Password
)
$ErrorActionPreference='Stop'
$s=[IO.Ports.SerialPort]::new($PortName,115200,[IO.Ports.Parity]::None,8,[IO.Ports.StopBits]::One)
$s.DtrEnable=$false
$s.RtsEnable=$false
$ptr=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($Password)
$secret=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
function Read-Prompt([string]$Pattern,[int]$Seconds=12) {
    $result=''
    $deadline=[DateTime]::UtcNow.AddSeconds($Seconds)
    while([DateTime]::UtcNow -lt $deadline) {
        $chunk=$s.ReadExisting()
        $result+=$chunk
        if($result -match $Pattern){return $result}
        # Only answer a live cursor-position request, never inject escape data later.
        if($chunk.Contains(([string][char]27)+'[6n')){$s.Write(([string][char]27)+'[24;80R')}
        Start-Sleep -Milliseconds 40
    }
    throw ('Prompt timeout: '+$result)
}
try {
    $s.Open()
    $s.Write("`r")
    $r=Read-Prompt '(?m)(login:|[#\$])\s*$'
    if($r -match 'login:\s*$') {
        $s.Write($Username+"`r")
        $r=Read-Prompt '(?mi)(password:|[#\$])\s*$'
        if($r -match '(?i)password:\s*$') {
            $s.Write($secret+"`r")
            $r=Read-Prompt '(?mi)(Retype new password:|[#\$]|Login incorrect)\s*$'
            if($r -match 'Retype new password:\s*$') {
                $s.Write($secret+"`r")
                $r=Read-Prompt '(?m)[#\$]\s*$'
            }
        }
    }
    if($r -match '\$\s*$') {
        $s.Write("sudo -s`r")
        $r=Read-Prompt '(?mi)(password.*:|#)\s*$'
        if($r -match '(?i)password.*:\s*$') {
            $s.Write($secret+"`r")
            $r=Read-Prompt '(?m)#\s*$'
        }
    }
    if($r -notmatch '#\s*$'){throw 'Root shell not confirmed; no commands sent.'}
    Write-Output "Root shell ready on $PortName. Password was not saved."
} finally {
    if($s.IsOpen){$s.Close()}
    $s.Dispose()
    $secret=$null
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
}
