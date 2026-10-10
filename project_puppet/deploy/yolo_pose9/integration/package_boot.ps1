$ErrorActionPreference='Stop'
$release=Split-Path $PSScriptRoot
$source=Join-Path (Split-Path $release) 'dpu_arm_chain\petalinux_release\sd1_uboot_fixed'
$output=Join-Path $release 'sd_candidate'
$bit='C:\WZH_File\codex_camera_ila_20260921\production_output\shadow_ultra_dpu_video_reset.bit'
New-Item -ItemType Directory $output -Force | Out-Null
foreach($name in @('fsbl_sd1_debug.elf','pmufw.elf','bl31.elf','u-boot.elf','system.dtb')) {
 Copy-Item -LiteralPath (Join-Path $source $name) -Destination (Join-Path $output $name)
}
Copy-Item -LiteralPath $bit -Destination (Join-Path $output 'system.bit')
Copy-Item -LiteralPath (Join-Path $source 'boot_sd1_uboot_fixed.bif') -Destination (Join-Path $output 'boot.bif')
Push-Location $output
try {
 & 'D:\WZH_Programs\Vitis2022\Vivado\2022.2\bin\bootgen.bat' -arch zynqmp -image boot.bif -o BOOT.BIN -w on
 if($LASTEXITCODE -ne 0){throw 'bootgen failed'}
 Copy-Item BOOT.BIN (Join-Path $release 'rollback\BOOT.BIN')
 Get-FileHash BOOT.BIN -Algorithm SHA256
} finally { Pop-Location }
