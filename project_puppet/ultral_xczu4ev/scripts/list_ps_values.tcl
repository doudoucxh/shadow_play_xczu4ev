create_project -force ps_value_test [file normalize "ultral_xczu4ev/tmp/ps_value_test"] -part xczu4ev-sfvc784-2-i
create_bd_design system
set ps [create_bd_cell -type ip -vlnv xilinx.com:ip:zynq_ultra_ps_e:* zynq_ultra_ps_e_0]
foreach p {CONFIG.PSU__DDRC__VENDOR_PART CONFIG.PSU__DDRC__PARTNO CONFIG.PSU__DDRC__SPEED_BIN CONFIG.PSU__DDRC__MEMORY_TYPE CONFIG.PSU__DDRC__DRAM_WIDTH CONFIG.PSU__DDRC__DEVICE_CAPACITY CONFIG.PSU__DDRC__BG_ADDR_COUNT CONFIG.PSU__UART0__PERIPHERAL__IO} {
  puts "$p values=[list_property_value $p $ps]"
}
exit
