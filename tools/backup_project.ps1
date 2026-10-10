param(
    [Parameter(Mandatory=$true)][string]$Message,
    [Parameter(Mandatory=$true)][string[]]$Paths,
    [switch]$Push,
    [string]$Python
)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $taskRoot
try {
    & git diff --cached --quiet
    if ($LASTEXITCODE -ne 0) { throw 'The index already contains changes. Review them separately before using this helper.' }
    if (-not $Python) {
        $bundledPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
        if (Test-Path -LiteralPath $bundledPython) { $Python = $bundledPython }
        else { $Python = (Get-Command python -ErrorAction Stop).Source }
    }
    & git add -- @Paths
    if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }
    & $Python (Join-Path $PSScriptRoot 'check_git_backup.py')
    if ($LASTEXITCODE -ne 0) { throw 'Backup check failed. Staged files were preserved for review; nothing was committed or pushed.' }
    & git diff --cached --quiet
    if ($LASTEXITCODE -eq 0) { Write-Output 'No changes to commit.'; return }
    & git commit -m $Message
    if ($LASTEXITCODE -ne 0) { throw 'git commit failed. Local files were preserved.' }
    & git log -1 --format='%h %s'
    if ($Push) {
        $remoteUrl = (& git remote get-url origin).Trim()
        if ($remoteUrl -ne 'https://github.com/doudoucxh/shadow_play_xczu4ev.git') { throw 'Unexpected origin; refusing to push.' }
        $branchName = (& git branch --show-current).Trim()
        if (-not $branchName) { throw 'Detached HEAD; commit is saved locally but not pushed.' }
        & git push -u origin $branchName
        if ($LASTEXITCODE -ne 0) { throw 'Push failed; the commit remains backed up locally.' }
    }
} finally {
    Pop-Location
}
