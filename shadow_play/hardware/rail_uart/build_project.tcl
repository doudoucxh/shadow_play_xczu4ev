set rail_here [file dirname [file normalize [info script]]]
set rail_output [file normalize [file join $rail_here ../../../.review_work/rail_uart_20261019]]
set_param general.maxThreads 4
open_project [file join $rail_output servo10_dual_uart servo10_dual_uart.xpr]
config_ip_cache -disable_cache
launch_runs synth_1 -jobs 3
wait_on_run synth_1
if {[get_property PROGRESS [get_runs synth_1]] != "100%"} {error "Rail UART synthesis failed"}
launch_runs impl_1 -to_step route_design -jobs 3
wait_on_run impl_1
if {[get_property PROGRESS [get_runs impl_1]] != "100%"} {error "Rail UART implementation failed"}
open_run impl_1
set output $rail_output
source [file join $rail_here ../servo_pwm/validate_open_design.tcl]
foreach {rail_port rail_pin rail_direction} {person_uart_tx F15 OUT person_uart_rx H13 IN tiger_uart_tx H14 OUT tiger_uart_rx L13 IN} {
    set rail_p [get_ports $rail_port]
    if {[llength $rail_p] != 1 || [get_property PACKAGE_PIN $rail_p] ne $rail_pin ||
        [get_property IOSTANDARD $rail_p] ne "LVCMOS33" || [get_property DIRECTION $rail_p] ne $rail_direction} {
        error "Unexpected rail UART pin/direction/voltage: $rail_port"
    }
}
puts "RAIL_UART_DESIGN_CHECKS_PASS"
write_checkpoint -force [file join $rail_output dual_uart_verified.dcp]
write_bitstream -force [file join $rail_output servo10_dual_uart.bit]
puts "RAIL_UART_BITSTREAM_READY"
close_project
