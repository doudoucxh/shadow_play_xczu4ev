set script_dir [file dirname [file normalize [info script]]]
set root_dir [file normalize [file join $script_dir ..]]
open_project [file join $root_dir dpu vivado_dpu Shadow_ultra_dpu.xpr]
set r [get_runs system_dpu_0_0_synth_1]
reset_run $r
launch_runs $r -jobs 2
wait_on_run $r
set status [get_property STATUS $r]
puts "DPU_CORE_STATUS=$status"
if {![string match "*Complete*" $status]} {
  error "DPU core synthesis failed: $status"
}
close_project
exit 0
