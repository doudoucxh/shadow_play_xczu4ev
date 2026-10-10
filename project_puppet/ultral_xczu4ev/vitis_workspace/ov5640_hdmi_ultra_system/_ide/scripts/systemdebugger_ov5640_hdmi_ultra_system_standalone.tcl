# Usage with Vitis IDE:
# In Vitis IDE create a Single Application Debug launch configuration,
# change the debug type to 'Attach to running target' and provide this 
# tcl script in 'Execute Script' option.
# Path of this script: E:\xilinx_project\ZYNQ_project\Shadow_play\ultral_xczu4ev\vitis_workspace\ov5640_hdmi_ultra_system\_ide\scripts\systemdebugger_ov5640_hdmi_ultra_system_standalone.tcl
# 
# 
# Usage with xsct:
# To debug using xsct, launch xsct and run below command
# source E:\xilinx_project\ZYNQ_project\Shadow_play\ultral_xczu4ev\vitis_workspace\ov5640_hdmi_ultra_system\_ide\scripts\systemdebugger_ov5640_hdmi_ultra_system_standalone.tcl
# 
connect -url tcp:127.0.0.1:3121
source E:/Vitis/2022.2/scripts/vitis/util/zynqmp_utils.tcl
targets -set -nocase -filter {name =~"APU*"}
rst -system
after 3000
targets -set -nocase -filter {name =~"APU*"}
loadhw -hw E:/xilinx_project/ZYNQ_project/Shadow_play/ultral_xczu4ev/vitis_workspace/Shadow_ultra_platform/export/Shadow_ultra_platform/hw/Shadow_ultra.xsa -mem-ranges [list {0x80000000 0xbfffffff} {0x400000000 0x5ffffffff} {0x1000000000 0x7fffffffff}] -regs
configparams force-mem-access 1
targets -set -nocase -filter {name =~"APU*"}
set mode [expr [mrd -value 0xFF5E0200] & 0xf]
targets -set -nocase -filter {name =~ "*A53*#0"}
rst -processor
dow E:/xilinx_project/ZYNQ_project/Shadow_play/ultral_xczu4ev/vitis_workspace/Shadow_ultra_platform/export/Shadow_ultra_platform/sw/Shadow_ultra_platform/boot/fsbl.elf
set bp_22_7_fsbl_bp [bpadd -addr &XFsbl_Exit]
con -block -timeout 60
bpremove $bp_22_7_fsbl_bp
targets -set -nocase -filter {name =~ "*A53*#0"}
rst -processor
dow E:/xilinx_project/ZYNQ_project/Shadow_play/ultral_xczu4ev/vitis_workspace/ov5640_hdmi_ultra/Debug/ov5640_hdmi_ultra.elf
configparams force-mem-access 0
targets -set -nocase -filter {name =~ "*A53*#0"}
con
