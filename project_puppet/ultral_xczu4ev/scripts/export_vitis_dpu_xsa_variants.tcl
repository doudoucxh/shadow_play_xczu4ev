set script_dir [file dirname [file normalize [info script]]]
set root_dir [file normalize [file join $script_dir ..]]
set dpu_root [file join $root_dir dpu]
set build_dir [file join $dpu_root build]

open_project [file join $dpu_root vivado_dpu Shadow_ultra_dpu.xpr]
set_property top system_wrapper [current_fileset]
update_compile_order -fileset sources_1
write_hw_platform -fixed -hw -force [file join $build_dir Shadow_ultra_dpu_project_hw.xsa]

open_checkpoint [file join $build_dir system_wrapper_dpu_b4096_synth.dcp]
set_property top system_wrapper [current_fileset]
write_hw_platform -fixed -hw -force [file join $build_dir Shadow_ultra_dpu_checkpoint_hw.xsa]
puts "PASS: exported project and checkpoint hardware-XSA variants"
exit 0
