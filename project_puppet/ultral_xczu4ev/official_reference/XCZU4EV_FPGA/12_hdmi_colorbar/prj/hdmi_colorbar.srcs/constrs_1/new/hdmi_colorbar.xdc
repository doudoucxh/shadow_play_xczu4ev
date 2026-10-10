#IO管脚约束
#时钟周期约束
create_clock -period 10.000 -name sys_clk_p [get_ports sys_clk_p]
#时钟
set_property IOSTANDARD DIFF_HSTL_I_12 [get_ports sys_clk_p]
set_property IOSTANDARD DIFF_HSTL_I_12 [get_ports sys_clk_n]
set_property PACKAGE_PIN AE5 [get_ports sys_clk_p]
set_property PACKAGE_PIN AF5 [get_ports sys_clk_n]
#复位
set_property -dict {PACKAGE_PIN AH11 IOSTANDARD LVCMOS33} [get_ports sys_rst_n]
#HDMI
set_property -dict {PACKAGE_PIN G3 IOSTANDARD LVDS} [get_ports {tmds_data_p[2]}]
set_property -dict {PACKAGE_PIN F2 IOSTANDARD LVDS} [get_ports {tmds_data_p[1]}]
set_property -dict {PACKAGE_PIN G1 IOSTANDARD LVDS} [get_ports {tmds_data_p[0]}]
set_property -dict {PACKAGE_PIN E1 IOSTANDARD LVDS} [get_ports tmds_clk_p]

