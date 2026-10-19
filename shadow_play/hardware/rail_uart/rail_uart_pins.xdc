# Owner report, 2026-10-19: motor RX -> FPGA TX; motor TX -> FPGA RX.
# Both drivers use TTL UART and share GND with the FPGA.
set_property -dict {PACKAGE_PIN F15 IOSTANDARD LVCMOS33 DRIVE 4 SLEW SLOW} [get_ports person_uart_tx]
set_property -dict {PACKAGE_PIN H13 IOSTANDARD LVCMOS33} [get_ports person_uart_rx]
set_property -dict {PACKAGE_PIN H14 IOSTANDARD LVCMOS33 DRIVE 4 SLEW SLOW} [get_ports tiger_uart_tx]
set_property -dict {PACKAGE_PIN L13 IOSTANDARD LVCMOS33} [get_ports tiger_uart_rx]
