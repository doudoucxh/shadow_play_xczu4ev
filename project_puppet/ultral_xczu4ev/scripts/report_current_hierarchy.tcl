set script_dir [file dirname [file normalize [info script]]]
set root_dir [file normalize [file join $script_dir ..]]
open_project [file join $root_dir vivado Shadow_ultra.xpr]
open_run impl_1
report_utilization -hierarchical -hierarchical_depth 3 -file [file join $root_dir reports current_hierarchical_utilization.rpt]
close_project
exit 0
