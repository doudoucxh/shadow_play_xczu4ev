# Probe DPUCZDX8G v4.1 configuration values without changing the HDMI project.
set script_dir [file dirname [file normalize [info script]]]
set root_dir   [file normalize [file join $script_dir ..]]
set probe_dir  [file join $root_dir dpu probe_project]
set ip_repo    [file join $root_dir dpu DPUCZDX8G_ip_repo_VAI_v3.0]

file mkdir $probe_dir
create_project -force dpu_probe $probe_dir -part xczu4ev-sfvc784-2-i
set_property ip_repo_paths [list $ip_repo] [current_project]
update_ip_catalog

set dpu_defs [get_ipdefs -all -filter {VLNV == "xilinx.com:ip:dpuczdx8g:4.1"}]
if {[llength $dpu_defs] != 1} {
  puts "DPU_PROBE_ERROR: expected DPUCZDX8G v4.1, found: $dpu_defs"
  exit 2
}

create_bd_design dpu_probe_bd
create_bd_cell -type ip -vlnv xilinx.com:ip:dpuczdx8g:4.1 dpu_probe
set dpu [get_bd_cells dpu_probe]

puts "DPU_PROBE_VLNV=[get_property VLNV $dpu]"
foreach p [lsort [list_property $dpu]] {
  if {[string match "CONFIG.*" $p]} {
    set v [get_property $p $dpu]
    puts "DPU_PROPERTY $p=$v"
  }
}

close_project
exit 0
