set script_dir [file dirname [file normalize [info script]]]
set root_dir [file normalize [file join $script_dir ..]]
set dpu_root [file join $root_dir dpu]
set project_file [file join $dpu_root vivado_dpu Shadow_ultra_dpu.xpr]
set output_file [file join $dpu_root build Shadow_ultra_dpu_b4096_vitis.xsa]

open_project $project_file
set_property top system_wrapper [current_fileset]
update_compile_order -fileset sources_1

# Export from the project source database so the XSA records TopModuleName and
# a Vitis-readable HwDb.  The verified routed bitstream is distributed beside
# this hardware-description XSA and is not regenerated here.
write_hw_platform -fixed -force $output_file
puts "PASS: generated Vitis-readable DPU hardware-description XSA: $output_file"
exit 0
