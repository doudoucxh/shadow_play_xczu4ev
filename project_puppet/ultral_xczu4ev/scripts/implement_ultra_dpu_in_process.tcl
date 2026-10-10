set script_dir [file dirname [file normalize [info script]]]
set root_dir [file normalize [file join $script_dir ..]]
set dpu_root [file join $root_dir dpu]
set report_dir [file join $dpu_root reports]
set build_dir [file join $dpu_root build]
file mkdir $report_dir
file mkdir $build_dir

open_project [file join $dpu_root vivado_dpu Shadow_ultra_dpu.xpr]
open_checkpoint [file join $build_dir system_wrapper_dpu_b4096_synth.dcp]

opt_design
report_utilization -file [file join $report_dir post_opt_utilization.rpt]

place_design
phys_opt_design
report_utilization -hierarchical -hierarchical_depth 3 -file [file join $report_dir post_place_utilization.rpt]
report_timing_summary -max_paths 20 -file [file join $report_dir post_place_timing.rpt]

route_design
report_utilization -hierarchical -hierarchical_depth 3 -file [file join $report_dir post_route_utilization.rpt]
report_timing_summary -max_paths 20 -file [file join $report_dir post_route_timing.rpt]
report_drc -file [file join $report_dir post_route_drc.rpt]
report_route_status -file [file join $report_dir post_route_status.rpt]

set worst_path [get_timing_paths -delay_type max -max_paths 1 -nworst 1]
if {[llength $worst_path] == 0} {
  error "No setup timing path was available after route_design"
}
set route_wns [get_property SLACK $worst_path]
puts "Post-route WNS: $route_wns ns"
if {$route_wns < 0.0} {
  error "Refusing to generate a release bitstream: post-route timing failed with WNS=$route_wns ns"
}

set bit_file [file join $build_dir system_wrapper_dpu_b4096.bit]
write_bitstream -force $bit_file

set arch_json [file join $dpu_root vivado_dpu Shadow_ultra_dpu.gen sources_1 bd system ip system_dpu_0_0 arch.json]
file copy -force $arch_json [file join $build_dir arch_b4096.json]
write_hw_platform -fixed -include_bit -force [file join $build_dir Shadow_ultra_dpu_b4096.xsa]

puts "PASS: implemented B4096 DPU design and generated timing-clean bitstream/XSA (WNS=$route_wns ns)"
exit 0
