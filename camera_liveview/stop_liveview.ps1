$ErrorActionPreference = 'Stop'
$pointer = Join-Path $PSScriptRoot 'output\current.json'
if(-not (Test-Path -LiteralPath $pointer)){Write-Host 'No live-view session recorded.';exit 0}
$session = Get-Content -LiteralPath $pointer -Raw | ConvertFrom-Json
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'output')) + [IO.Path]::DirectorySeparatorChar
$folder = [IO.Path]::GetFullPath($session.directory)
if(-not $folder.StartsWith($root,[StringComparison]::OrdinalIgnoreCase)){throw 'Unexpected session path.'}
[IO.File]::WriteAllText((Join-Path $folder 'stop.request'), 'stop')
Write-Host 'Live-view stop requested.'
