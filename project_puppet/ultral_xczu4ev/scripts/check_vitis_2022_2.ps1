$ErrorActionPreference = 'Stop'
$root = if ($env:XILINX_VITIS) { $env:XILINX_VITIS } else { 'D:\xilinx\Vitis\2022.2' }
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$logDir = Join-Path $projectRoot 'deploy\logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir 'vitis_2022_2_preflight.txt'

& {
    "checked_at=$([DateTime]::Now.ToString('o'))"
    "XILINX_VITIS=$root"
    $xsct = Join-Path $root 'bin\xsct.bat'
    "xsct=$xsct exists=$(Test-Path -LiteralPath $xsct)"
    $compiler = Get-ChildItem -LiteralPath $root -Recurse -Filter 'aarch64-none-elf-gcc.exe' -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty FullName
    "aarch64_none_elf_gcc=$compiler"
    $bootgen = Get-ChildItem -LiteralPath 'D:\xilinx' -Recurse -Filter 'bootgen.bat' -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty FullName
    "bootgen=$bootgen"
    if (Test-Path -LiteralPath $xsct) {
        "xsct_help_begin"
        & $xsct -help 2>&1
        "xsct_help_end"
    }
    if (!(Test-Path -LiteralPath $xsct) -or !$compiler -or !$bootgen) {
        throw 'Full Vitis 2022.2 preflight failed; see the paths above.'
    }
} 2>&1 | Tee-Object -FilePath $log
"PASS log=$log"
