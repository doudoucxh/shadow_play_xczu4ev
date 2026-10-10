set script_dir [file dirname [file normalize [info script]]]
set root_dir [file normalize [file join $script_dir ..]]
open_project [file join $root_dir dpu vivado_dpu Shadow_ultra_dpu.xpr]

set runs [lsort [get_runs -quiet -filter {IS_SYNTHESIS == 1 && NAME != synth_1}]]
if {[llength $runs] == 0} { error "No DPU OOC synthesis runs exist" }

foreach r $runs {
  set status [get_property STATUS $r]
  if {[string match "*Complete*" $status]} {
    puts "DPU_OOC_SKIP $r ($status)"
    continue
  }
  puts "DPU_OOC_START $r"
  reset_run $r
  launch_runs $r -jobs 2
  wait_on_run $r
  set status [get_property STATUS $r]
  puts "DPU_OOC_DONE $r ($status)"
  if {![string match "*Complete*" $status]} {
    error "DPU OOC synthesis failed: $r ($status)"
  }
}

close_project
puts "PASS: all DPU OOC synthesis runs completed"
exit 0
