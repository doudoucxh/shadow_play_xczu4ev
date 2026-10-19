# Explicit owner-requested direction trial; not the reported production wiring.
# DRIVE 4 selects the weakest output strength; it is not a hard current limit.
set_property -dict {PACKAGE_PIN H13 IOSTANDARD LVCMOS33 DRIVE 4 SLEW SLOW} [get_ports person_uart_tx]
set_property -dict {PACKAGE_PIN F15 IOSTANDARD LVCMOS33} [get_ports person_uart_rx]
set_property -dict {PACKAGE_PIN L13 IOSTANDARD LVCMOS33 DRIVE 4 SLEW SLOW} [get_ports tiger_uart_tx]
set_property -dict {PACKAGE_PIN H14 IOSTANDARD LVCMOS33} [get_ports tiger_uart_rx]
