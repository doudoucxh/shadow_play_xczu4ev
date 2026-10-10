set script_dir [file dirname [file normalize [info script]]]
set root_dir [file dirname $script_dir]
set xpr [file join $root_dir vivado Shadow_ultra.xpr]
set report_dir [file join $root_dir reports]
file mkdir $report_dir

open_project $xpr
# Rebuild all generated IP products.  The HDMI block now comes directly from
# the official MPSoC-P4 OV5640-to-HDMI example rather than a module reference.
set ip_cache_dir [file join $root_dir vivado Shadow_ultra.cache ip]
if {[file exists $ip_cache_dir]} {
  file delete -force $ip_cache_dir
  puts "INFO: cleared local IP cache"
}
open_bd_design [get_files system.bd]
update_compile_order -fileset sources_1
validate_bd_design
save_bd_design
generate_target all [get_files system.bd]
reset_run synth_1
launch_runs synth_1 -jobs 8
wait_on_run synth_1
if {[get_property PROGRESS [get_runs synth_1]] ne "100%"} {
  error "Synthesis did not complete: [get_property STATUS [get_runs synth_1]]"
}
open_run synth_1
report_utilization -file [file join $report_dir post_synth_utilization.rpt]
report_timing_summary -file [file join $report_dir post_synth_timing.rpt]

launch_runs impl_1 -to_step write_bitstream -jobs 8
wait_on_run impl_1
if {[get_property PROGRESS [get_runs impl_1]] ne "100%"} {
  error "Implementation did not complete: [get_property STATUS [get_runs impl_1]]"
}
open_run impl_1
report_utilization -file [file join $report_dir post_route_utilization.rpt]
report_timing_summary -max_paths 20 -file [file join $report_dir post_route_timing.rpt]
report_drc -file [file join $report_dir post_route_drc.rpt]
set generated_bit [file join $root_dir vivado Shadow_ultra.runs impl_1 system_wrapper.bit]
set staged_bit [file join $root_dir build system_wrapper.bit]
file mkdir [file dirname $staged_bit]
file copy -force $generated_bit $staged_bit
write_hw_platform -fixed -include_bit -force [file join $root_dir Shadow_ultra.xsa]
puts "PASS: staged bitstream and Shadow_ultra.xsa generated"
exit
