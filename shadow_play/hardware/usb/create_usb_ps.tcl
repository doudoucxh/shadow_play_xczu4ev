# Generate a PS-only handoff for the FSBL. Never synthesize/replace the PL.
set here [file dirname [file normalize [info script]]]
set workspace [file normalize [file join $here ../../..]]
set out [file join $workspace .review_work usb_camera_20261010 ps_usb]
if {[file exists [file join $out ps_usb.xpr]]} {
    open_project [file join $out ps_usb.xpr]
    open_bd_design [get_files system.bd]
    set ps [get_bd_cells zynq_ultra_ps_e_0]
} else {
    create_project ps_usb $out -part xczu4ev-sfvc784-2-i
    create_bd_design system
    set ps [create_bd_cell -type ip -vlnv xilinx.com:ip:zynq_ultra_ps_e:3.4 zynq_ultra_ps_e_0]
    source [file join $here original_ps_config.tcl]
}
set_property -dict [list \
    CONFIG.PSU__USB0__PERIPHERAL__ENABLE {1} \
    CONFIG.PSU__USB0__PERIPHERAL__IO {MIO 52 .. 63} \
    CONFIG.PSU__USB__RESET__MODE {Shared MIO Pin} \
    CONFIG.PSU__USB__RESET__POLARITY {Active Low} \
    CONFIG.PSU__USB0__RESET__ENABLE {1} \
    CONFIG.PSU__USB0__RESET__IO {MIO 24} \
    CONFIG.PSU__USB0__REF_CLK_FREQ {100} \
    CONFIG.PSU__USB3_0__PERIPHERAL__ENABLE {0} \
    CONFIG.PSU__USB1__PERIPHERAL__ENABLE {0}] $ps
# The handoff needs a valid standalone BD; these connections are never used
# to synthesize the existing PL image.
foreach pin [get_bd_pins -of_objects $ps -filter {TYPE == clk && DIR == I}] {
    if {![llength [get_bd_nets -quiet -of_objects $pin]]} {
        connect_bd_net [get_bd_pins $ps/pl_clk0] $pin
    }
}
save_bd_design
generate_target all [get_files system.bd]
write_hw_platform -fixed -force -file [file join $out usb_ps.xsa]
puts "USB_PS_HANDOFF_READY [file join $out usb_ps.xsa]"
close_project
