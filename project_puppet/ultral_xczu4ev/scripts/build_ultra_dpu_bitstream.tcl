set script_dir [file dirname [file normalize [info script]]]
set root_dir [file normalize [file join $script_dir ..]]
set dpu_root [file join $root_dir dpu]
set xpr [file join $dpu_root vivado_dpu Shadow_ultra_dpu.xpr]
set report_dir [file join $dpu_root reports]
set build_dir [file join $dpu_root build]
file mkdir $report_dir
file mkdir $build_dir

open_project $xpr
open_bd_design [get_files system.bd]
update_compile_order -fileset sources_1
validate_bd_design
save_bd_design
generate_target all [get_files system.bd]

reset_run synth_1
launch_runs synth_1 -jobs 8
wait_on_run synth_1
if {[get_property PROGRESS [get_runs synth_1]] ne "100%"} {
  error "DPU synthesis did not complete: [get_property STATUS [get_runs synth_1]]"
}
open_run synth_1
report_utilization -hierarchical -hierarchical_depth 3 -file [file join $report_dir post_synth_utilization.rpt]
report_timing_summary -file [file join $report_dir post_synth_timing.rpt]

launch_runs impl_1 -to_step write_bitstream -jobs 8
wait_on_run impl_1
if {[get_property PROGRESS [get_runs impl_1]] ne "100%"} {
  error "DPU implementation did not complete: [get_property STATUS [get_runs impl_1]]"
}
open_run impl_1
report_utilization -hierarchical -hierarchical_depth 3 -file [file join $report_dir post_route_utilization.rpt]
report_timing_summary -max_paths 20 -file [file join $report_dir post_route_timing.rpt]
report_drc -file [file join $report_dir post_route_drc.rpt]

set generated_bit [file join $dpu_root vivado_dpu Shadow_ultra_dpu.runs impl_1 system_wrapper.bit]
file copy -force $generated_bit [file join $build_dir system_wrapper_dpu_b4096.bit]
set arch_json [file join $dpu_root vivado_dpu Shadow_ultra_dpu.gen sources_1 bd system ip system_dpu_0_0 arch.json]
file copy -force $arch_json [file join $build_dir arch_b4096.json]
write_hw_platform -fixed -include_bit -force [file join $build_dir Shadow_ultra_dpu_b4096.xsa]
puts "PASS: B4096 DPU bitstream, XSA and arch.json generated in $build_dir"
exit 0
