set script_dir [file dirname [file normalize [info script]]]
set root_dir [file normalize [file join $script_dir ..]]
set xpr [file join $root_dir dpu vivado_dpu Shadow_ultra_dpu.xpr]

open_project $xpr
open_bd_design [get_files system.bd]
set clkgen [get_bd_cells clk_wiz_video]
set ps [get_bd_cells zynq_ultra_ps_e_0]
# A 100.004023 MHz propagated PL clock makes Clocking Wizard choose the exact
# 1125/15, /6, /3 MMCM ratios. At 99.999281 MHz it chooses fractional ratios,
# producing 75.035 and 188.759 MHz and impossible 0.083 ns HDMI timing paths.
set_property CONFIG.PSU__CRL_APB__PL0_REF_CTRL__FREQMHZ {100.004023} $ps
set_property CONFIG.OVERRIDE_MMCM {true} $clkgen
set_property -dict [list \
  CONFIG.MMCM_DIVCLK_DIVIDE {1} \
  CONFIG.MMCM_CLKFBOUT_MULT_F {11.250} \
  CONFIG.MMCM_CLKOUT0_DIVIDE_F {15.000} \
  CONFIG.MMCM_CLKOUT1_DIVIDE {6} \
  CONFIG.MMCM_CLKOUT2_DIVIDE {3}] $clkgen
validate_bd_design
save_bd_design
generate_target all [get_files system.bd]
set expected [dict create \
  CONFIG.MMCM_DIVCLK_DIVIDE 1 \
  CONFIG.MMCM_CLKFBOUT_MULT_F 11.250 \
  CONFIG.MMCM_CLKOUT0_DIVIDE_F 15.000 \
  CONFIG.MMCM_CLKOUT1_DIVIDE 6 \
  CONFIG.MMCM_CLKOUT2_DIVIDE 3]
dict for {property wanted} $expected {
  set actual [get_property $property $clkgen]
  if {[expr {double($actual) != double($wanted)}]} {
    error "Clocking Wizard did not select the safe HDMI ratio: $property=$actual, expected $wanted"
  }
}
set clock_run [get_runs -quiet system_clk_wiz_video_0_synth_1]
if {[llength $clock_run] != 1} {
  error "Expected system_clk_wiz_video_0_synth_1 OOC run, got: $clock_run"
}
reset_run $clock_run
launch_runs $clock_run -jobs 2
wait_on_run $clock_run
if {[get_property PROGRESS $clock_run] ne "100%"} {
  error "Video clock OOC synthesis failed: [get_property STATUS $clock_run]"
}
set run_dcp [file join [get_property DIRECTORY $clock_run] system_clk_wiz_video_0.dcp]
set generated_dcp [file join $root_dir dpu vivado_dpu Shadow_ultra_dpu.gen \
  sources_1 bd system ip system_clk_wiz_video_0 system_clk_wiz_video_0.dcp]
file copy -force $run_dcp $generated_dcp
puts "PASS: fixed DPU video MMCM at exact 75/187.5/375 MHz ratios"
close_project
exit 0
