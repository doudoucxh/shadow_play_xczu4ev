$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '../tools/board_shell_guard.ps1')
class FakeBoardSerial {
    [Collections.Generic.Queue[string]]$Chunks
    [Collections.Generic.List[string]]$Writes
    FakeBoardSerial([string[]]$chunks) {
        $this.Chunks = [Collections.Generic.Queue[string]]::new()
        foreach ($chunk in $chunks) { $this.Chunks.Enqueue($chunk) }
        $this.Writes = [Collections.Generic.List[string]]::new()
    }
    [string]ReadExisting() {
        if ($this.Chunks.Count) { return $this.Chunks.Dequeue() }
        return ''
    }
    [void]Write([string]$value) { $this.Writes.Add($value) }
}
foreach ($prompt in @('shadowdpupetalinux:/home/petalinux#', 'root@shadowdpupetalinux:~#', 'petalinux@board:~$', '#', 'bash-5.1#')) {
    $serial = [FakeBoardSerial]::new(@($prompt))
    Wait-BoardShell $serial -TimeoutMilliseconds 100
    if ($serial.Writes.Count) { throw 'Ready shell must not receive extra input' }
}
foreach ($prompt in @('shadowdpupetalinux login:', 'Password:', 'New password:', 'Retype new password:', '[sudo] password for petalinux:')) {
    $serial = [FakeBoardSerial]::new(@($prompt))
    $blocked = $false
    try { Wait-BoardShell $serial -TimeoutMilliseconds 100 } catch { $blocked = $_.ToString().Contains('authentication prompt') }
    if (-not $blocked -or $serial.Writes.Count) { throw 'Authentication prompt received input' }
}
$serial = [FakeBoardSerial]::new(@('', 'shadowdpupetalinux:/home/petalinux#'))
Wait-BoardShell $serial -TimeoutMilliseconds 100
if ($serial.Writes.Count -ne 1 -or $serial.Writes[0] -ne "`r") { throw 'Unexpected prompt request' }
$serial = [FakeBoardSerial]::new(@('BOOTING'))
$blocked = $false
try { Wait-BoardShell $serial -TimeoutMilliseconds 50 } catch { $blocked = $_.ToString().Contains('No live board shell') }
if (-not $blocked -or $serial.Writes.Count -ne 1 -or $serial.Writes[0] -ne "`r") { throw 'Unknown prompt accepted' }
Write-Output 'PASS: 12 shell/login/timeout protocol cases; no hardware accessed.'
