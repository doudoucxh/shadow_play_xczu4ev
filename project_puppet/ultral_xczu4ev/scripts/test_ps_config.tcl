create_project -force ps_config_test [file normalize "ultral_xczu4ev/tmp/ps_config_test"] -part xczu4ev-sfvc784-2-i
create_bd_design system
set ps [create_bd_cell -type ip -vlnv xilinx.com:ip:zynq_ultra_ps_e:* zynq_ultra_ps_e_0]
set cfg [list \
  CONFIG.PSU__DDRC__ENABLE {1} \
  CONFIG.PSU__USE__DDR_INTF_REQUESTED {1} \
  CONFIG.PSU__DDRC__VENDOR_PART {DDR4_SAMSUNG_K4A8G165WB_BCRC} \
  CONFIG.PSU__DDRC__MEMORY_TYPE {DDR 4} \
  CONFIG.PSU__DDRC__COMPONENTS {Components} \
  CONFIG.PSU__DDRC__BUS_WIDTH {64 Bit} \
  CONFIG.PSU__DDRC__BG_ADDR_COUNT {1} \
  CONFIG.PSU__DDRC__DRAM_WIDTH {16 Bits} \
  CONFIG.PSU__DDRC__DEVICE_CAPACITY {4096 MBits} \
  CONFIG.PSU__DDRC__ROW_ADDR_COUNT {15} \
  CONFIG.PSU__UART0__PERIPHERAL__ENABLE {1} \
  CONFIG.PSU__UART0__PERIPHERAL__IO {MIO 42 .. 43} \
  CONFIG.PSU__GPIO_EMIO__PERIPHERAL__ENABLE {1} \
  CONFIG.PSU__GPIO_EMIO_WIDTH {2} \
  CONFIG.PSU__USE__M_AXI_GP0 {1} \
  CONFIG.PSU__USE__S_AXI_GP2 {1} \
  CONFIG.PSU__FPGA_PL0_ENABLE {1} \
  CONFIG.PSU__CRL_APB__PL0_REF_CTRL__FREQMHZ {200}]
foreach {p v} $cfg {
  if {[lsearch -exact [list_property $ps] $p] < 0} {
    puts "MISSING $p"
  } elseif {[catch {set_property $p $v $ps} err]} {
    puts "FAILED $p=$v : $err"
  } else {
    puts "SET $p=[get_property $p $ps]"
  }
}
puts "INTERFACES: [get_bd_intf_pins $ps/*]"
puts "PINS: [get_bd_pins $ps/*]"
save_bd_design
validate_bd_design
exit
