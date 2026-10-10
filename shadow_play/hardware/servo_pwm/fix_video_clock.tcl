# Restore the proven video MMCM divisors both in the BD and routed checkpoint.
# No false paths or relaxed timing requirements are added.
set here [file dirname [file normalize [info script]]]
set output [file normalize [file join $here ../../../.review_work/servo_capture_20261008/fpga]]
set_param general.maxThreads 4
open_project [file join $output servo10_dpu servo10_dpu.xpr]
config_ip_cache -disable_cache
open_bd_design [get_files system.bd]
set_property -dict [list CONFIG.OVERRIDE_MMCM true CONFIG.MMCM_DIVCLK_DIVIDE 1 \
    CONFIG.MMCM_CLKFBOUT_MULT_F 11.250 CONFIG.MMCM_CLKOUT0_DIVIDE_F 15.000 \
    CONFIG.MMCM_CLKOUT1_DIVIDE 6 CONFIG.MMCM_CLKOUT2_DIVIDE 3] [get_bd_cells clk_wiz_video]
validate_bd_design
save_bd_design
generate_target all [get_files system.bd]
write_bd_tcl -force [file join $output servo10_design_fixed.tcl]
close_project
open_checkpoint [file join $output servo10_dpu servo10_dpu.runs impl_1 system_wrapper_routed.dcp]
set mmcm [get_cells system_i/clk_wiz_video/inst/mmcme4_adv_inst]
if {[llength $mmcm]!=1} {error "Expected one video MMCM"}
set_property -dict [list DIVCLK_DIVIDE 1 CLKFBOUT_MULT_F 11.250 \
    CLKOUT0_DIVIDE_F 15.000 CLKOUT1_DIVIDE 6 CLKOUT2_DIVIDE 3] $mmcm
update_timing
report_timing_summary -file [file join $output corrected_clock_initial_timing.rpt]
write_checkpoint -force [file join $output servo10_clock_corrected.dcp]
set setup [get_property SLACK [get_timing_paths -delay_type max -max_paths 1]]
set hold [get_property SLACK [get_timing_paths -delay_type min -max_paths 1]]
puts "CORRECTED_CLOCK_TIMING WNS=$setup WHS=$hold"
if {$hold < 0} {
    phys_opt_design -hold_fix
    route_design -preserve
}
source [file join $here validate_open_design.tcl]
write_checkpoint -force [file join $output servo10_verified.dcp]
write_bitstream -force [file join $output servo10_vision.bit]
puts "SERVO_FIXED_CLOCK_BITSTREAM_READY"
close_design
