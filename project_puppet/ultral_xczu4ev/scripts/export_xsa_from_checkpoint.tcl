set script_dir [file dirname [file normalize [info script]]]
set root_dir [file dirname $script_dir]
set proj_dir [file join $root_dir vivado]
set build_dir [file join $root_dir build]

open_project [file join $proj_dir Shadow_ultra.xpr]
open_checkpoint [file join $build_dir system_wrapper_routed.dcp]
write_hw_platform -fixed -force [file join $root_dir Shadow_ultra.xsa]
puts "PASS: hardware XSA exported from routed checkpoint"
exit
