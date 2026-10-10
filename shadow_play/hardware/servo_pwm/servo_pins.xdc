# Physical package pins supplied by the owner on 2026-10-08.
# PWM uses the existing 3.3 V PL IO bank standard; never apply servo power to IO.
set_property -dict {PACKAGE_PIN D14 IOSTANDARD LVCMOS33 DRIVE 4 SLEW SLOW} [get_ports {servo_pwm[0]}]
set_property -dict {PACKAGE_PIN D15 IOSTANDARD LVCMOS33 DRIVE 4 SLEW SLOW} [get_ports {servo_pwm[1]}]
set_property -dict {PACKAGE_PIN F13 IOSTANDARD LVCMOS33 DRIVE 4 SLEW SLOW} [get_ports {servo_pwm[2]}]
set_property -dict {PACKAGE_PIN G13 IOSTANDARD LVCMOS33 DRIVE 4 SLEW SLOW} [get_ports {servo_pwm[3]}]
set_property -dict {PACKAGE_PIN G14 IOSTANDARD LVCMOS33 DRIVE 4 SLEW SLOW} [get_ports {servo_pwm[4]}]
set_property -dict {PACKAGE_PIN G15 IOSTANDARD LVCMOS33 DRIVE 4 SLEW SLOW} [get_ports {servo_pwm[5]}]
set_property -dict {PACKAGE_PIN J14 IOSTANDARD LVCMOS33 DRIVE 4 SLEW SLOW} [get_ports {servo_pwm[6]}]
set_property -dict {PACKAGE_PIN E13 IOSTANDARD LVCMOS33 DRIVE 4 SLEW SLOW} [get_ports {servo_pwm[7]}]
set_property -dict {PACKAGE_PIN E14 IOSTANDARD LVCMOS33 DRIVE 4 SLEW SLOW} [get_ports {servo_pwm[8]}]
set_property -dict {PACKAGE_PIN E15 IOSTANDARD LVCMOS33 DRIVE 4 SLEW SLOW} [get_ports {servo_pwm[9]}]
