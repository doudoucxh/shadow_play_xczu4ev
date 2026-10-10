set script_dir [file dirname [file normalize [info script]]]
set root_dir [file normalize [file join $script_dir ..]]
set xpr [file join $root_dir dpu vivado_dpu Shadow_ultra_dpu.xpr]
open_project $xpr
open_bd_design [get_files system.bd]
set ps [get_bd_cells zynq_ultra_ps_e_0]
puts "=== PS AXI interface pins ==="
foreach p [lsort [get_bd_intf_pins -of_objects $ps]] {
  puts "$p MODE=[get_property MODE $p] VLNV=[get_property VLNV $p]"
}
puts "=== Current relevant PS properties ==="
foreach p [lsort [list_property $ps]] {
  if {[regexp {PSU__USE__([MS]_AXI|IRQ)|PSU__MAXIGP|PSU__SAXIGP} $p]} {
    puts "$p=[get_property $p $ps]"
  }
}
close_project
exit 0
