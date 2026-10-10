set script_dir [file dirname [file normalize [info script]]]
set root_dir [file normalize [file join $script_dir ..]]
open_project [file join $root_dir dpu vivado_dpu Shadow_ultra_dpu.xpr]
set bd_file [lindex [get_files -quiet */system.bd] 0]
if {$bd_file eq ""} { error "system.bd not found" }
open_bd_design $bd_file
generate_target all $bd_file
create_ip_run $bd_file
puts "DPU_OOC_RUNS_BEGIN"
foreach r [lsort [get_runs -quiet -filter {IS_SYNTHESIS == 1 && NAME != synth_1}]] {
  puts "$r|[get_property STATUS $r]|[get_property DIRECTORY $r]"
}
puts "DPU_OOC_RUNS_END"
close_project
exit 0
