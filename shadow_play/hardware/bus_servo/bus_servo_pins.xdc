# Original PWM 9 and 10 connectors are now BIDIRECTIONAL. External 3.3 V
# compatibility is mandatory; internal weak pull-ups are only idle bias.
set_property -dict {PACKAGE_PIN E14 IOSTANDARD LVCMOS33 DRIVE 4 SLEW SLOW PULLUP true} [get_ports person_servo_bus]
set_property -dict {PACKAGE_PIN E15 IOSTANDARD LVCMOS33 DRIVE 4 SLEW SLOW PULLUP true} [get_ports tiger_servo_bus]
