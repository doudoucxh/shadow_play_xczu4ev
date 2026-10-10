[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$Program,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $Program"
    }
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$workspace = if ($env:VITIS_WORKSPACE) {
    [IO.Path]::GetFullPath($env:VITIS_WORKSPACE)
} else {
    Join-Path $projectRoot 'vitis_workspace_2022_2'
}
$vitisRoot = if ($env:XILINX_VITIS) {
    [IO.Path]::GetFullPath($env:XILINX_VITIS)
} else {
    'D:\xilinx\Vitis\2022.2'
}

$toolRoot = Join-Path $vitisRoot 'gnu\aarch64\nt\aarch64-none\bin'
$compiler = Join-Path $toolRoot 'aarch64-none-elf-gcc.exe'
$sizeTool = Join-Path $toolRoot 'aarch64-none-elf-size.exe'
$readelf = Join-Path $toolRoot 'aarch64-none-elf-readelf.exe'
$sourceRoot = Join-Path $projectRoot 'vitis\ov5640_hdmi\src'
$appRoot = Join-Path $workspace 'ov5640_hdmi_ultra'
$appSource = Join-Path $appRoot 'src'
$outputRoot = Join-Path $appRoot 'Debug'
$objectRoot = Join-Path $outputRoot 'obj'
$elf = Join-Path $outputRoot 'ov5640_hdmi_ultra.elf'
$bspRoot = Join-Path $workspace 'Shadow_ultra_platform\export\Shadow_ultra_platform\sw\Shadow_ultra_platform\standalone_domain'
$bspInclude = Join-Path $bspRoot 'bspinclude\include'
$bspLib = Join-Path $bspRoot 'bsplib\lib'
$linker = Join-Path $sourceRoot 'lscript.ld'

$required = @($compiler, $sizeTool, $readelf, $sourceRoot, $bspInclude, $bspLib, $linker)
foreach ($item in $required) {
    if (-not (Test-Path -LiteralPath $item)) {
        throw "Required Vitis build input is missing: $item"
    }
}

$sources = @(
    'main.c',
    'display_ctrl_hdmi\display_ctrl_hdmi.c',
    'emio_sccb_cfg\emio_sccb_cfg.c',
    'ov5640\ov5640_init.c',
    'vdma_api\vdma_api.c'
)
foreach ($relative in $sources) {
    if (-not (Test-Path -LiteralPath (Join-Path $sourceRoot $relative))) {
        throw "Expected firmware source is missing: $relative"
    }
}
$actualSources = @(Get-ChildItem -LiteralPath $sourceRoot -Recurse -Filter '*.c' | ForEach-Object {
    $_.FullName.Substring($sourceRoot.Length + 1)
})
if (@(Compare-Object -ReferenceObject $sources -DifferenceObject $actualSources).Count -ne 0) {
    throw "Firmware C source set changed. Update the audited source list before building."
}

New-Item -ItemType Directory -Force -Path $appSource, $objectRoot | Out-Null
Get-ChildItem -LiteralPath $sourceRoot -Recurse -File | Where-Object Name -ne 'lscript.ld' | ForEach-Object {
    $relative = $_.FullName.Substring($sourceRoot.Length + 1)
    $destination = Join-Path $appSource $relative
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destination) | Out-Null
    Copy-Item -LiteralPath $_.FullName -Destination $destination -Force
}

$commonFlags = @(
    '-Wall', '-Wextra', '-O2', '-g',
    '-ffunction-sections', '-fdata-sections',
    '-fmessage-length=0',
    "-I$bspInclude", "-I$appSource"
)
$objects = @()
foreach ($relative in $sources) {
    $object = Join-Path $objectRoot ($relative -replace '\.c$', '.o')
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $object) | Out-Null
    Invoke-Checked $compiler (@($commonFlags) + @('-c', (Join-Path $appSource $relative), '-o', $object))
    $objects += $object
}

$linkArguments = @(
    "-Wl,-T,$linker",
    "-L$bspLib",
    '-Wl,--gc-sections',
    '-o', $elf
) + $objects + @(
    '-Wl,--start-group', '-lxil', '-lgcc', '-lc', '-Wl,--end-group'
)
Invoke-Checked $compiler $linkArguments
Invoke-Checked $sizeTool @($elf)

$headerLines = & $readelf -h $elf
if ($LASTEXITCODE -ne 0) {
    throw 'readelf failed while checking the generated ELF.'
}
$header = $headerLines -join "`n"
if (($header -notmatch 'Class:\s+ELF64') -or
    ($header -notmatch 'Data:\s+2.s complement, little endian') -or
    ($header -notmatch 'Machine:\s+AArch64')) {
    throw "Generated ELF is not a little-endian AArch64 ELF64 executable.`n$header"
}

$sha256 = [Security.Cryptography.SHA256]::Create()
try {
    $stream = [IO.File]::OpenRead($elf)
    try {
        $elfHash = ([BitConverter]::ToString($sha256.ComputeHash($stream))).Replace('-', '').ToLowerInvariant()
    } finally {
        $stream.Dispose()
    }
} finally {
    $sha256.Dispose()
}
Write-Output "elf=$elf"
Write-Output "elf_sha256=$elfHash"
Write-Output 'PASS: Vitis 2022.2 A53 firmware built and architecture-checked.'
