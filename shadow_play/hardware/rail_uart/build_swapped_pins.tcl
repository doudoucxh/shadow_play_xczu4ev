# Local ECO from the verified routed dual-UART checkpoint. No hardware access.
set here [file dirname [file normalize [info script]]]
set workspace [file normalize [file join $here ../../..]]
set output [file join $workspace .review_work rail_uart_swapped_20261019]
file mkdir $output
if {[file exists [file join $output servo10_uart_swapped.bit]]} {error "Swapped bitstream already exists"}
set_param general.maxThreads 4
open_checkpoint [file join $workspace .review_work rail_uart_20261019 dual_uart_verified.dcp]
set names {person_uart_tx person_uart_rx tiger_uart_tx tiger_uart_rx}
set old_pins {F15 H13 H14 L13}
set new_pins {H13 F15 L13 H14}
set buffers [list]
set original_ports [dict create]
foreach p [get_ports] {
    if {[lsearch -exact $names $p] < 0} {
        dict set original_ports $p [list [get_property PACKAGE_PIN $p] [get_property DIRECTION $p] [get_property IOSTANDARD $p]]
    }
}
foreach name $names pin $old_pins {
    set port [get_ports $name]
    if {[get_property PACKAGE_PIN $port] ne $pin} {error "Unexpected source pin: $name"}
    set cell [get_cells -of_objects [get_nets -of_objects $port]]
    if {[llength $cell] != 1 || [get_property REF_NAME $cell] ni {OBUF IBUF}} {error "Unexpected I/O buffer: $name"}
    lappend buffers $cell
}
set nets [get_nets -of_objects [get_pins -of_objects [get_cells $buffers]]]
route_design -unroute -nets $nets
unplace_cell [get_cells $buffers]
reset_property LOC [get_cells $buffers]
reset_property BEL [get_cells $buffers]
reset_property PACKAGE_PIN [get_ports $names]
source [file join $here rail_uart_swapped_pins.xdc]
foreach name $names pin $new_pins cell $buffers {
    set site [get_sites -of_objects [get_package_pins $pin]]
    if {[llength $site] != 1 || [get_property BANK [get_package_pins $pin]] != 46} {error "Unexpected UART site/bank"}
    place_cell [list $cell $site]
}
route_design -preserve
dict for {name expected} $original_ports {
    set p [get_ports $name]
    if {[list [get_property PACKAGE_PIN $p] [get_property DIRECTION $p] [get_property IOSTANDARD $p]] ne $expected} {
        error "Unrelated port changed: $name"
    }
}
foreach name $names pin $new_pins direction {OUT IN OUT IN} {
    set p [get_ports $name]
    if {[get_property PACKAGE_PIN $p] ne $pin || [get_property DIRECTION $p] ne $direction ||
        [get_property IOSTANDARD $p] ne "LVCMOS33"} {error "Swapped UART pin check failed"}
    if {$direction eq "OUT" && [get_property DRIVE $p] != 4} {error "Unexpected TX drive strength"}
}
source [file join $here ../servo_pwm/validate_open_design.tcl]
puts "RAIL_UART_SWAPPED_DESIGN_CHECKS_PASS"
write_checkpoint -force [file join $output uart_swapped_verified.dcp]
write_bitstream -force [file join $output servo10_uart_swapped.bit]
puts "RAIL_UART_SWAPPED_BITSTREAM_READY"
close_design
