# ATK-OV5640 single-camera pinout supplied by the board owner.
# MPSoC-P4 J19 camera signal group, using XCZU4EV package-pin names.

create_clock -period 13.888 -name cam_pclk [get_ports cam_pclk]
set_property CLOCK_DEDICATED_ROUTE FALSE [get_nets -hier -filter {NAME =~ *cam_pclk_IBUF*}]

# SCCB (PS GPIO via EMIO 0/1)
set_property -dict {PACKAGE_PIN D10 IOSTANDARD LVCMOS33 PULLUP TRUE} [get_ports cam_scl]
set_property -dict {PACKAGE_PIN E10 IOSTANDARD LVCMOS33 PULLUP TRUE} [get_ports cam_sda]

# OV5640 8-bit DVP data bus
set_property -dict {PACKAGE_PIN B10 IOSTANDARD LVCMOS33} [get_ports {cam_data[0]}]
set_property -dict {PACKAGE_PIN B11 IOSTANDARD LVCMOS33} [get_ports {cam_data[1]}]
set_property -dict {PACKAGE_PIN C11 IOSTANDARD LVCMOS33} [get_ports {cam_data[2]}]
set_property -dict {PACKAGE_PIN C12 IOSTANDARD LVCMOS33} [get_ports {cam_data[3]}]
set_property -dict {PACKAGE_PIN A11 IOSTANDARD LVCMOS33} [get_ports {cam_data[4]}]
set_property -dict {PACKAGE_PIN D12 IOSTANDARD LVCMOS33} [get_ports {cam_data[5]}]
set_property -dict {PACKAGE_PIN A12 IOSTANDARD LVCMOS33} [get_ports {cam_data[6]}]
set_property -dict {PACKAGE_PIN A14 IOSTANDARD LVCMOS33} [get_ports {cam_data[7]}]

set_property -dict {PACKAGE_PIN A15 IOSTANDARD LVCMOS33} [get_ports cam_pclk]
set_property -dict {PACKAGE_PIN D11 IOSTANDARD LVCMOS33} [get_ports cam_vsync]
set_property -dict {PACKAGE_PIN E12 IOSTANDARD LVCMOS33} [get_ports cam_href]
set_property -dict {PACKAGE_PIN B15 IOSTANDARD LVCMOS33} [get_ports cam_pwdn]
set_property -dict {PACKAGE_PIN A10 IOSTANDARD LVCMOS33} [get_ports cam_rst_n]
set_property -dict {PACKAGE_PIN B14 IOSTANDARD LVCMOS33} [get_ports cam_flash]
