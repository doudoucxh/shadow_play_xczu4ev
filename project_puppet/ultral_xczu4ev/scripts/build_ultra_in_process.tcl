set script_dir [file dirname [file normalize [info script]]]
set root_dir [file dirname $script_dir]
set proj_dir [file join $root_dir vivado]
set report_dir [file join $root_dir reports]
set build_dir [file join $root_dir build]
file mkdir $report_dir
file mkdir $build_dir

open_project [file join $proj_dir Shadow_ultra.xpr]
update_compile_order -fileset sources_1
synth_design -top system_wrapper -part xczu4ev-sfvc784-2-i -flatten_hierarchy rebuilt
set black_boxes [get_cells -hier -filter {IS_BLACKBOX}]
if {[llength $black_boxes] != 0} {
  error "Black boxes remain after synthesis: $black_boxes"
}
write_checkpoint -force [file join $build_dir system_wrapper_synth.dcp]
report_utilization -file [file join $report_dir post_synth_utilization.rpt]
report_timing_summary -file [file join $report_dir post_synth_timing.rpt]

opt_design
place_design
phys_opt_design
route_design
write_checkpoint -force [file join $build_dir system_wrapper_routed.dcp]
report_utilization -file [file join $report_dir post_route_utilization.rpt]
report_timing_summary -delay_type min_max -report_unconstrained \
  -max_paths 20 -file [file join $report_dir post_route_timing.rpt]
report_route_status -file [file join $report_dir post_route_status.rpt]
report_drc -file [file join $report_dir post_route_drc.rpt]
write_bitstream -force [file join $build_dir system_wrapper.bit]
write_hw_platform -fixed -force [file join $root_dir Shadow_ultra.xsa]
set package_script [file join $script_dir package_xsa_with_bitstream.ps1]
set package_result [exec powershell.exe -NoProfile -ExecutionPolicy Bypass \
  -File $package_script]
puts $package_result
puts "PASS: in-process implementation, bitstream, and complete XSA generated"
exit
