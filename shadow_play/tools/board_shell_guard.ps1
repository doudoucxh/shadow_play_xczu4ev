# Accept only a live shell prompt before sending a command or file payload.
function Wait-BoardShell {
    param($Serial, [string]$Initial = '', [int]$TimeoutMilliseconds = 8000)
    $seen = $Initial
    $requested = $false
    $deadline = [DateTime]::UtcNow.AddMilliseconds($TimeoutMilliseconds)
    while ($true) {
        $seen += $Serial.ReadExisting()
        $plain = [regex]::Replace($seen, '\x1b\[[0-?]*[ -/]*[@-~]', '').TrimEnd()
        $last = ($plain -split "`n")[-1].Trim()
        if ($last -match '(?i)(login:|(?:new |retype new )?password[^:]*:)\s*$') {
            throw 'Board is at an authentication prompt; no command or password was sent. Log in first.'
        }
        if ($last -match '^(?:[^\s@]+@[^\s:]+:[^\r\n]*|[^\s:]+:[^\r\n]*|(?:ba)?sh(?:-[0-9.]+)?)?[#$]$') {
            return
        }
        if (-not $requested) {
            # A single empty line requests the current prompt; never send stty,
            # a payload, or credentials until the shell itself is recognized.
            $Serial.Write("`r")
            $requested = $true
        }
        if ([DateTime]::UtcNow -ge $deadline) {
            throw 'No live board shell prompt; no deployment command was sent.'
        }
        Start-Sleep -Milliseconds 40
    }
}
