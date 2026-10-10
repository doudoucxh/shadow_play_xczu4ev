set script_dir [file dirname [file normalize [info script]]]
set root_dir [file normalize [file join $script_dir ..]]
open_project [file join $root_dir dpu vivado_dpu Shadow_ultra_dpu.xpr]
foreach r [get_runs] {
  puts "RUN_STATUS $r STATUS=[get_property STATUS $r] PROGRESS=[get_property PROGRESS $r] NEEDS_REFRESH=[get_property NEEDS_REFRESH $r]"
}
foreach ip [get_ips] {
  puts "IP_STATUS $ip STATUS=[get_property STATUS $ip]"
}
close_project
exit 0
