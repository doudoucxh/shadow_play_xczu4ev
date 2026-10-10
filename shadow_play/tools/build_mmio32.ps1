param([string]$VitisRoot = 'D:\xilinx\Vitis\2022.2')
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot
$compiler=Join-Path $VitisRoot 'gnu\aarch64\nt\aarch64-linux\bin\aarch64-linux-gnu-gcc.exe'
$dump=Join-Path $VitisRoot 'gnu\aarch64\nt\aarch64-linux\x86_64-petalinux-mingw32\usr\bin\aarch64-xilinx-linux\aarch64-xilinx-linux-objdump.exe'
$source=Join-Path $root 'integrations\calibration\mmio32.c'
$output=Join-Path $root 'integrations\calibration\libservo_mmio32.so'
& $compiler -std=c11 -O2 -Wall -Wextra -Werror -fPIC -shared -nostdlib -fno-stack-protector -fno-builtin '-Wl,-z,noexecstack' $source -o $output
if($LASTEXITCODE -ne 0){throw 'MMIO native library compilation failed'}
& $dump -d $output
if($LASTEXITCODE -ne 0){throw 'Cannot inspect MMIO library'}
Write-Output 'Check: servo_mmio_read32 uses ldr w; write32 uses str w; both surrounded by dsb sy.'
