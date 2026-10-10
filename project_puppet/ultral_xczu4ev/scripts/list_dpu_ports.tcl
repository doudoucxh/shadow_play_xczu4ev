set script_dir [file dirname [file normalize [info script]]]
set root_dir [file normalize [file join $script_dir ..]]
set xpr [file join $root_dir dpu matrix_project dpu_matrix.xpr]
open_project $xpr
open_bd_design [get_files dpu_matrix_bd.bd]
set dpu [get_bd_cells dpu_0]
puts "DPU_INTERFACES_BEGIN"
foreach p [lsort [get_bd_intf_pins -of_objects $dpu]] {
  puts "DPU_INTF $p MODE=[get_property MODE $p] VLNV=[get_property VLNV $p]"
}
puts "DPU_PINS_BEGIN"
foreach p [lsort [get_bd_pins -of_objects $dpu]] {
  puts "DPU_PIN $p DIR=[get_property DIR $p] TYPE=[get_property TYPE $p]"
}
close_project
exit 0
