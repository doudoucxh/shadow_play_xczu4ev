# Program the MPSoC-P4 PL, initialize the PS with the generated FSBL, then
# download and run the bare-metal camera/HDMI application on Cortex-A53 #0.
# Prefer program_and_run.bat: it enforces the generated pre-board safety gate
# before this script is allowed to touch JTAG.

set script_dir   [file dirname [file normalize [info script]]]
set project_root [file normalize [file join $script_dir ..]]
if {[info exists ::env(VITIS_WORKSPACE)] && $::env(VITIS_WORKSPACE) ne ""} {
    set workspace [file normalize $::env(VITIS_WORKSPACE)]
} else {
    set workspace [file join $project_root vitis_workspace_2022_2]
}
set bit_file     [file join $project_root build system_wrapper.bit]
set xsa_file     [file join $project_root Shadow_ultra.xsa]
set fsbl_file    [file join $workspace Shadow_ultra_platform export Shadow_ultra_platform sw Shadow_ultra_platform boot fsbl.elf]
set app_file     [file join $workspace ov5640_hdmi_ultra Debug ov5640_hdmi_ultra.elf]
set ps_init_file [file join $workspace Shadow_ultra_platform hw psu_init.tcl]

proc stage {message} {
    puts ""
    puts "==== $message ===="
    flush stdout
}

stage "Checking programming files"
foreach required_file [list $bit_file $xsa_file $fsbl_file $app_file $ps_init_file] {
    if {![file exists $required_file]} {
        error "Required programming file is missing: $required_file"
    }
}

stage "Connecting to hardware server"
connect -url tcp:127.0.0.1:3121
if {[info exists ::env(XILINX_VITIS)] && $::env(XILINX_VITIS) ne ""} {
    set vitis_root [file normalize $::env(XILINX_VITIS)]
} else {
    set vitis_root [file normalize D:/xilinx/Vitis/2022.2]
}
set zynqmp_utils [file join $vitis_root scripts vitis util zynqmp_utils.tcl]
if {![file exists $zynqmp_utils]} {
    error "zynqmp_utils.tcl is missing under $vitis_root; install full Vitis 2022.2 or set XILINX_VITIS"
}
source $zynqmp_utils
jtag targets -set -filter {level == 0}
jtag frequency 5000000

stage "Resetting Zynq UltraScale+ system"
targets -set -nocase -filter {name =~ "APU*"}
rst -system
after 3000

stage "Loading hardware description"
targets -set -nocase -filter {name =~ "APU*"}
loadhw -hw $xsa_file \
    -mem-ranges [list {0x80000000 0xbfffffff} {0x400000000 0x5ffffffff} {0x1000000000 0x7fffffffff}] \
    -regs
configparams force-mem-access 1

stage "Running FSBL and initializing PS/DDR/clocks"
targets -set -nocase -filter {name =~ "*A53*#0"}
rst -processor
dow $fsbl_file
set fsbl_exit_breakpoint [bpadd -addr &XFsbl_Exit]
con -block -timeout 60
bpremove $fsbl_exit_breakpoint

# Program the already timing-closed PL image only after PS/DDR initialization.
stage "Programming PL bitstream"
fpga -file $bit_file
after 1000

# A bitstream downloaded with the XSCT "fpga" command is not a partition in
# the FSBL boot image.  Consequently the FSBL does not execute its normal
# post-bitstream PS/PL handoff.  Perform that handoff explicitly so the PL AXI
# slaves are accessible and the fabric reset reaches the generated design.
stage "Releasing PS-PL isolation and PL reset"
source $ps_init_file
psu_ps_pl_isolation_removal
psu_ps_pl_reset_config
after 1000

stage "Checking video VDMA, pose VDMA and HLS AXI access"
foreach {probe_name probe_address} {
    video_vdma 0xA0000000
    pose_vdma  0xA0010000
    pose_hls   0xA0020000
} {
    if {[catch {set probe_value [mrd -force -value $probe_address]} probe_error]} {
        error "$probe_name AXI register access failed after reset release: $probe_error"
    }
    set probe_value [expr {wide($probe_value) & 0xFFFFFFFF}]
    if {$probe_name eq "pose_hls" && ($probe_value & 0xFFFFFF70) != 0} {
        error [format "pose_hls returned invalid AXI control value 0x%08X at 0x%08X" $probe_value $probe_address]
    }
    puts [format "%s register is reachable: 0x%08X" $probe_name $probe_value]
}
flush stdout

stage "Downloading camera and HDMI application to Cortex-A53 #0"
targets -set -nocase -filter {name =~ "*A53*#0"}
rst -processor
dow $app_file
configparams force-mem-access 0
con

stage "Download complete"
puts "PL configured and ov5640_hdmi_ultra started on Cortex-A53 #0."
flush stdout
