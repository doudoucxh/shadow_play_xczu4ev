# Build a separate project, preserving the working vision/SD project.
set here [file dirname [file normalize [info script]]]
set workspace [file normalize [file join $here ../../..]]
set original [file join $workspace project_puppet ultral_xczu4ev]
set output [file join $workspace .review_work servo_capture_20261008 fpga]
file mkdir $output
set export_bd [file join $output vision_base.tcl]
open_project -read_only [file join $original dpu vivado_dpu Shadow_ultra_dpu.xpr]
open_bd_design [get_files system.bd]
write_bd_tcl -force $export_bd
close_project
set project_dir [file join $output servo10_dpu]
if {[file exists [file join $project_dir servo10_dpu.xpr]]} {error "New project already exists; resume it explicitly instead of overwriting"}
create_project servo10_dpu $project_dir -part xczu4ev-sfvc784-2-i
set_property target_language Verilog [current_project]
set_property ip_repo_paths [list [file join $original ip_repo DVI_TX] [file join $original dpu DPUCZDX8G_ip_repo_VAI_v3.0]] [current_project]
update_ip_catalog
foreach name {emio_sccb_bridge ov5640_capture_data pose_preprocess_axis} {
    add_files -norecurse [file join $original rtl ${name}.v]
}
add_files -norecurse [file join $here servo_pwm_axi.v]
update_compile_order -fileset sources_1
source $export_bd
# BD export may carry stale automatically calculated MMCM values. Preserve the
# actual working video-clock primitive: 1125 MHz VCO -> 75 / 187.5 / 375 MHz.
set_property -dict [list CONFIG.OVERRIDE_MMCM true CONFIG.MMCM_DIVCLK_DIVIDE 1 \
    CONFIG.MMCM_CLKFBOUT_MULT_F 11.250 CONFIG.MMCM_CLKOUT0_DIVIDE_F 15.000 \
    CONFIG.MMCM_CLKOUT1_DIVIDE 6 CONFIG.MMCM_CLKOUT2_DIVIDE 3] [get_bd_cells clk_wiz_video]
set ctrl [get_bd_cells axi_control]
if {[get_property CONFIG.NUM_MI $ctrl] != 3} {error "Unexpected existing AXI layout; review before adding PWM"}
set_property CONFIG.NUM_MI 4 $ctrl
set pwm [create_bd_cell -type module -reference servo_pwm_axi servo_pwm_0]
connect_bd_intf_net [get_bd_intf_pins $ctrl/M03_AXI] [get_bd_intf_pins $pwm/S_AXI]
connect_bd_net [get_bd_pins clk_wiz_system/clk_out1] [get_bd_pins $pwm/aclk]
connect_bd_net [get_bd_pins rst_ps_100M/peripheral_aresetn] [get_bd_pins $pwm/aresetn]
set pwm_port [create_bd_port -dir O -from 9 -to 0 servo_pwm]
connect_bd_net $pwm_port [get_bd_pins $pwm/servo_pwm]
set pwm_seg [get_bd_addr_segs -of_objects [get_bd_intf_pins $pwm/S_AXI]]
if {[llength $pwm_seg]!=1} {error "Expected one PWM AXI register segment: $pwm_seg"}
assign_bd_address -offset 0xA0030000 -range 0x00010000 -target_address_space [get_bd_addr_spaces zynq_ultra_ps_e_0/Data] $pwm_seg -force
validate_bd_design
save_bd_design
add_files -fileset constrs_1 -norecurse [list [file join $original constraints camera_dvp.xdc] [file join $original constraints hdmi.xdc] [file join $here servo_pins.xdc]]
make_wrapper -files [get_files system.bd] -top
add_files -norecurse [file join $project_dir servo10_dpu.gen sources_1 bd system hdl system_wrapper.v]
set_property top system_wrapper [current_fileset]
update_compile_order -fileset sources_1
generate_target all [get_files system.bd]
write_bd_tcl -force [file join $output servo10_design.tcl]
# Package-pin checks are performed after synthesis, when a device design is open.
puts "SERVO_PROJECT_READY [file join $project_dir servo10_dpu.xpr]"
close_project
