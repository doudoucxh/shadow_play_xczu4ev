# Temporary tiger-only four independent single-wire buses. External 3.3V compatibility required.
set_property -dict {PACKAGE_PIN D14 IOSTANDARD LVCMOS33 DRIVE 4 SLEW SLOW PULLUP true} [get_ports tiger7_servo_bus]
set_property -dict {PACKAGE_PIN D15 IOSTANDARD LVCMOS33 DRIVE 4 SLEW SLOW PULLUP true} [get_ports tiger8_servo_bus]
set_property -dict {PACKAGE_PIN F13 IOSTANDARD LVCMOS33 DRIVE 4 SLEW SLOW PULLUP true} [get_ports tiger9_servo_bus]
set_property -dict {PACKAGE_PIN G13 IOSTANDARD LVCMOS33 DRIVE 4 SLEW SLOW PULLUP true} [get_ports tiger10_servo_bus]
