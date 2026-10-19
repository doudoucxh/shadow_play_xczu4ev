# Independent build only. Never programs PL or changes the existing project.
set rail_here [file dirname [file normalize [info script]]]
set rail_root [file normalize [file join $rail_here ../../..]]
set rail_output [file join $rail_root .review_work rail_uart_20261019]
set rail_project [file join $rail_output servo10_dual_uart]
if {[file exists $rail_project]} {error "Rail UART project exists; resume explicitly"}
file mkdir $rail_output
set rail_original [file join $rail_root project_puppet ultral_xczu4ev]
set rail_base [file join $rail_root .review_work servo_capture_20261008 fpga servo10_dpu servo10_dpu.xpr]
open_project -read_only $rail_base
open_bd_design [get_files system.bd]
write_bd_tcl -force [file join $rail_output servo_base.tcl]
close_project
create_project servo10_dual_uart $rail_project -part xczu4ev-sfvc784-2-i
set_property target_language Verilog [current_project]
set_property ip_repo_paths [list [file join $rail_original ip_repo DVI_TX] [file join $rail_original dpu DPUCZDX8G_ip_repo_VAI_v3.0]] [current_project]
update_ip_catalog
foreach module {emio_sccb_bridge ov5640_capture_data pose_preprocess_axis} {
    add_files -norecurse [file join $rail_original rtl ${module}.v]
}
add_files -norecurse [file join $rail_here ../servo_pwm/servo_pwm_axi.v]
update_compile_order -fileset sources_1
source [file join $rail_output servo_base.tcl]
set_property -dict [list CONFIG.OVERRIDE_MMCM true CONFIG.MMCM_DIVCLK_DIVIDE 1 \
    CONFIG.MMCM_CLKFBOUT_MULT_F 11.250 CONFIG.MMCM_CLKOUT0_DIVIDE_F 15.000 \
    CONFIG.MMCM_CLKOUT1_DIVIDE 6 CONFIG.MMCM_CLKOUT2_DIVIDE 3] [get_bd_cells clk_wiz_video]
set rail_control [get_bd_cells axi_control]
if {[get_property CONFIG.NUM_MI $rail_control] != 4} {error "Unexpected base AXI layout"}
set_property CONFIG.NUM_MI 6 $rail_control
foreach {rail_name rail_mi rail_address} {person 4 0xA0040000 tiger 5 0xA0050000} {
    set rail_uart [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_uartlite:2.0 ${rail_name}_uart]
    set_property -dict [list CONFIG.C_BAUDRATE 115200 CONFIG.C_DATA_BITS 8 CONFIG.C_USE_PARITY 0 CONFIG.C_ODD_PARITY 0] $rail_uart
    connect_bd_intf_net [get_bd_intf_pins [format {axi_control/M%02d_AXI} $rail_mi]] [get_bd_intf_pins $rail_uart/S_AXI]
    connect_bd_net [get_bd_pins clk_wiz_system/clk_out1] [get_bd_pins $rail_uart/s_axi_aclk]
    connect_bd_net [get_bd_pins rst_ps_100M/peripheral_aresetn] [get_bd_pins $rail_uart/s_axi_aresetn]
    connect_bd_net [create_bd_port -dir O ${rail_name}_uart_tx] [get_bd_pins $rail_uart/tx]
    connect_bd_net [create_bd_port -dir I ${rail_name}_uart_rx] [get_bd_pins $rail_uart/rx]
    assign_bd_address -offset $rail_address -range 0x00010000 -target_address_space [get_bd_addr_spaces zynq_ultra_ps_e_0/Data] [get_bd_addr_segs $rail_uart/S_AXI/Reg] -force
}
validate_bd_design
save_bd_design
add_files -fileset constrs_1 -norecurse [list [file join $rail_original constraints camera_dvp.xdc] \
    [file join $rail_original constraints hdmi.xdc] [file join $rail_here ../servo_pwm/servo_pins.xdc] \
    [file join $rail_here rail_uart_pins.xdc]]
make_wrapper -files [get_files system.bd] -top
add_files -norecurse [file join $rail_project servo10_dual_uart.gen sources_1 bd system hdl system_wrapper.v]
set_property top system_wrapper [current_fileset]
update_compile_order -fileset sources_1
generate_target all [get_files system.bd]
write_bd_tcl -force [file join $rail_output dual_uart_design.tcl]
puts "RAIL_UART_PROJECT_READY"
close_project
