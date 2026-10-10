set script_dir [file dirname [file normalize [info script]]]
set root_dir   [file dirname $script_dir]
open_project [file join $root_dir vivado Shadow_ultra.xpr]

set runs [lsort [get_runs -quiet -filter {IS_SYNTHESIS == 1 && NAME != synth_1}]]
if {[llength $runs] == 0} { error "No OOC synthesis runs exist" }

foreach r $runs {
  set status [get_property STATUS $r]
  if {[string match "*Complete*" $status] && [string match "*write_checkpoint Complete*" $status]} {
    puts "OOC_SKIP $r ($status)"
    continue
  }
  puts "OOC_START $r"
  reset_run $r
  launch_runs $r -jobs 1
  wait_on_run $r
  set status [get_property STATUS $r]
  puts "OOC_DONE $r ($status)"
  if {![string match "*Complete*" $status]} {
    error "OOC synthesis failed: $r ($status)"
  }
}

close_project
puts "PASS: all OOC synthesis runs completed"
exit
