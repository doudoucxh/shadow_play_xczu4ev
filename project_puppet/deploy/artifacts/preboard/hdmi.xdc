# MPSoC-P4 onboard HDMI transmitter pins from the board tutorial.
# The N pins are selected automatically through the differential OBUFDS pair.
set_property -dict {PACKAGE_PIN G3 IOSTANDARD LVDS} [get_ports {tmds_data_p[2]}]
set_property -dict {PACKAGE_PIN F2 IOSTANDARD LVDS} [get_ports {tmds_data_p[1]}]
set_property -dict {PACKAGE_PIN G1 IOSTANDARD LVDS} [get_ports {tmds_data_p[0]}]
set_property -dict {PACKAGE_PIN E1 IOSTANDARD LVDS} [get_ports tmds_clk_p]
