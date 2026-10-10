set script_dir [file dirname [file normalize [info script]]]
set root_dir [file normalize [file join $script_dir ..]]
open_project [file join $root_dir dpu vivado_dpu Shadow_ultra_dpu.xpr]
open_bd_design [get_files system.bd]
foreach cell_name {axi_memory axi_control dpu_0} {
  set c [get_bd_cells $cell_name]
  puts "CELL_BEGIN $cell_name"
  foreach p [lsort [list_property $c]] {
    if {[string match "CONFIG.*ID*" $p] || [string match "CONFIG.*PROTOCOL*" $p]} {
      puts "CELL_PROPERTY $cell_name $p=[get_property $p $c]"
    }
  }
}
close_project
exit 0
