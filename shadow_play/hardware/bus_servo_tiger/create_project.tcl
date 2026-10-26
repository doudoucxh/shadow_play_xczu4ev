# Offline independent candidate. No FPGA programming or boot-file changes.
set here [file dirname [file normalize [info script]]]
set root [file normalize [file join $here ../../..]]
set output [file join $root .review_work bus_servo_tiger_20261026]
set project_dir [file join $output bus_servo]
if {[file exists $project_dir]} {error "Candidate project exists; resume explicitly"}
file mkdir $output
set original [file join $root project_puppet ultral_xczu4ev]
# Frozen write_bd_tcl export of the existing dual-rail design. This is the
# same export used by the first build (canonical LF), retained to avoid depending
# on an ignored local .xpr cache when recreating the project.
set base [file join $here ../bus_servo/base_dual_rail_design.tcl]
create_project bus_servo $project_dir -part xczu4ev-sfvc784-2-i
set_property target_language Verilog [current_project]
set_property ip_repo_paths [list [file join $original ip_repo DVI_TX] [file join $original dpu DPUCZDX8G_ip_repo_VAI_v3.0]] [current_project]
update_ip_catalog
foreach module {emio_sccb_bridge ov5640_capture_data pose_preprocess_axis} {
    add_files -norecurse [file join $original rtl ${module}.v]
}
add_files -norecurse [list [file join $here ../servo_pwm/servo_pwm_axi.v] [file join $here ../bus_servo/single_wire_uart.v] [file join $here bus_servo_tiger_axi.v]]
update_compile_order -fileset sources_1
source $base
# Remove the physical legacy PWM port. SP10 remains software-visible for
# compatibility but has NO physical output and cannot drive either servo bus.
delete_bd_objs [get_bd_ports servo_pwm]
set_property -dict [list CONFIG.OVERRIDE_MMCM true CONFIG.MMCM_DIVCLK_DIVIDE 1 CONFIG.MMCM_CLKFBOUT_MULT_F 11.250 CONFIG.MMCM_CLKOUT0_DIVIDE_F 15.000 CONFIG.MMCM_CLKOUT1_DIVIDE 6 CONFIG.MMCM_CLKOUT2_DIVIDE 3] [get_bd_cells clk_wiz_video]
if {[get_property CONFIG.NUM_MI [get_bd_cells axi_control]] != 6} {error "Unexpected AXI layout"}
set_property CONFIG.NUM_MI 7 [get_bd_cells axi_control]
set controller [create_bd_cell -type module -reference bus_servo_tiger_axi bus_servo_0]
connect_bd_intf_net [get_bd_intf_pins axi_control/M06_AXI] [get_bd_intf_pins $controller/S_AXI]
connect_bd_net [get_bd_pins clk_wiz_system/clk_out1] [get_bd_pins $controller/aclk]
connect_bd_net [get_bd_pins rst_ps_100M/peripheral_aresetn] [get_bd_pins $controller/aresetn]
foreach {name direction} {bus_rx I bus_tx O bus_oe O} {
    connect_bd_net [create_bd_port -dir $direction -from 3 -to 0 $name] [get_bd_pins $controller/$name]
}
assign_bd_address -offset 0xA0060000 -range 0x00010000 -target_address_space [get_bd_addr_spaces zynq_ultra_ps_e_0/Data] [get_bd_addr_segs -of_objects [get_bd_intf_pins $controller/S_AXI]] -force
validate_bd_design
save_bd_design
add_files -fileset constrs_1 -norecurse [list [file join $original constraints camera_dvp.xdc] [file join $original constraints hdmi.xdc] [file join $here ../rail_uart/rail_uart_pins.xdc] [file join $here bus_servo_tiger_pins.xdc]]
source [file join $here finish_project.tcl]
