set script_dir [file dirname [file normalize [info script]]]
set root_dir [file normalize [file join $script_dir ..]]
set dpu_root [file join $root_dir dpu]
set report_dir [file join $dpu_root reports]
set build_dir [file join $dpu_root build]
file mkdir $report_dir
file mkdir $build_dir

open_project [file join $dpu_root vivado_dpu Shadow_ultra_dpu.xpr]
update_compile_order -fileset sources_1
synth_design -top system_wrapper -part xczu4ev-sfvc784-2-i -flatten_hierarchy rebuilt
set black_boxes [get_cells -hier -filter {IS_BLACKBOX}]
if {[llength $black_boxes] != 0} {
  error "Black boxes remain after DPU synthesis: $black_boxes"
}
write_checkpoint -force [file join $build_dir system_wrapper_dpu_b4096_synth.dcp]
report_utilization -hierarchical -hierarchical_depth 3 -file [file join $report_dir post_synth_utilization.rpt]
report_timing_summary -file [file join $report_dir post_synth_timing.rpt]
puts "PASS: B4096 DPU synthesis completed"
exit 0
