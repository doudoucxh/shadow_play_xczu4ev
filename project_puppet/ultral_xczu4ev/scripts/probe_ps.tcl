set out_dir [file normalize "ultral_xczu4ev/reports"]
file mkdir $out_dir
create_project -force ps_probe [file normalize "ultral_xczu4ev/tmp/ps_probe"] -part xczu4ev-sfvc784-2-i
create_bd_design probe
set ps [create_bd_cell -type ip -vlnv xilinx.com:ip:zynq_ultra_ps_e:* zynq_ultra_ps_e_0]
set fp [open [file join $out_dir ps_properties.txt] w]
foreach p [lsort [list_property $ps]] {
  if {[regexp -nocase {DDR|PL_CLK|GPIO|EMIO|HPM|HP[0-9]|HPC|UART|SD[01]|QSPI|TTC} $p]} {
    puts $fp "$p=[get_property $p $ps]"
  }
}
puts $fp "\nPINS:"
foreach p [lsort [get_bd_pins $ps/*]] {
  puts $fp "$p DIR=[get_property DIR $p] TYPE=[get_property TYPE $p]"
}
puts $fp "\nINTF_PINS:"
foreach p [lsort [get_bd_intf_pins $ps/*]] {
  puts $fp "$p MODE=[get_property MODE $p] VLNV=[get_property VLNV $p]"
}
close $fp
exit
