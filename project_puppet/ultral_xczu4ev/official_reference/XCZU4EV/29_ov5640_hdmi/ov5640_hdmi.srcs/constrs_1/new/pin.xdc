#----------------------摄像头接口的时钟---------------------------
#72M
create_clock -period 13.888 -name cam_pclk [get_ports cam_pclk]
set_property CLOCK_DEDICATED_ROUTE FALSE [get_nets cam_pclk_IBUF]

set_property -dict {PACKAGE_PIN C13 IOSTANDARD LVCMOS33} [get_ports cam_pclk]
set_property -dict {PACKAGE_PIN F13 IOSTANDARD LVCMOS33} [get_ports cam_rst_n]
set_property -dict {PACKAGE_PIN B15 IOSTANDARD LVCMOS33} [get_ports cam_pwdn]
set_property -dict {PACKAGE_PIN E15 IOSTANDARD LVCMOS33} [get_ports {cam_data[0]}]
set_property -dict {PACKAGE_PIN D15 IOSTANDARD LVCMOS33} [get_ports {cam_data[1]}]
set_property -dict {PACKAGE_PIN E14 IOSTANDARD LVCMOS33} [get_ports {cam_data[2]}]
set_property -dict {PACKAGE_PIN D14 IOSTANDARD LVCMOS33} [get_ports {cam_data[3]}]
set_property -dict {PACKAGE_PIN E13 IOSTANDARD LVCMOS33} [get_ports {cam_data[4]}]
set_property -dict {PACKAGE_PIN B13 IOSTANDARD LVCMOS33} [get_ports {cam_data[5]}]
set_property -dict {PACKAGE_PIN C14 IOSTANDARD LVCMOS33} [get_ports {cam_data[6]}]
set_property -dict {PACKAGE_PIN A13 IOSTANDARD LVCMOS33} [get_ports {cam_data[7]}]
set_property -dict {PACKAGE_PIN G14 IOSTANDARD LVCMOS33} [get_ports cam_vsync]
set_property -dict {PACKAGE_PIN G13 IOSTANDARD LVCMOS33} [get_ports cam_href]
set_property -dict {PACKAGE_PIN H13 IOSTANDARD LVCMOS33} [get_ports {emio_sccb_tri_io[0]}]
set_property -dict {PACKAGE_PIN F15 IOSTANDARD LVCMOS33} [get_ports {emio_sccb_tri_io[1]}]
set_property PULLUP true [get_ports {emio_sccb_tri_io[0]}]
set_property PULLUP true [get_ports {emio_sccb_tri_io[1]}]

#HDMI
set_property -dict {PACKAGE_PIN G3 IOSTANDARD LVDS} [get_ports {TMDS_tmds_data_p[2]}]
set_property -dict {PACKAGE_PIN F2 IOSTANDARD LVDS} [get_ports {TMDS_tmds_data_p[1]}]
set_property -dict {PACKAGE_PIN G1 IOSTANDARD LVDS} [get_ports {TMDS_tmds_data_p[0]}]
set_property -dict {PACKAGE_PIN E1 IOSTANDARD LVDS} [get_ports TMDS_tmds_clk_p]
