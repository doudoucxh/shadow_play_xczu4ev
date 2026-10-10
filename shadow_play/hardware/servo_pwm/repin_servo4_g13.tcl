# Reassign only servo 4's OBUF from H13 to G13 in the verified routed design.
# Preserve all other placement, routing, and the verified video-clock divisors.
set here [file dirname [file normalize [info script]]]
set workspace [file normalize [file join $here ../../..]]
set output [file join $workspace .review_work servo_pin4_g13_20261010 fpga]
file mkdir $output
set_param general.maxThreads 4
open_checkpoint [file join $workspace .review_work servo_capture_20261008 fpga servo10_verified.dcp]
set port [get_ports {servo_pwm[3]}]
if {[get_property PACKAGE_PIN $port] ne "H13"} {error "Unexpected source pin"}
if {[llength [get_ports -quiet -filter {PACKAGE_PIN == G13}]]} {error "G13 already occupied"}
set original_ports [dict create]
foreach p [get_ports] {
    if {$p ne $port} {dict set original_ports $p [get_property PACKAGE_PIN $p]}
}
set cell [get_cells -of_objects [get_nets -of_objects $port]]
if {[llength $cell] != 1 || [get_property REF_NAME $cell] ne "OBUF"} {error "Expected one output buffer"}
set site [get_sites -of_objects [get_package_pins G13]]
if {[llength $site] != 1 || [get_property BANK [get_package_pins G13]] != 46} {error "Unexpected G13 site/bank"}
set nets [get_nets -of_objects [get_pins -of_objects $cell]]
route_design -unroute -nets $nets
unplace_cell $cell
reset_property LOC $cell
reset_property BEL $cell
set_property PACKAGE_PIN G13 $port
place_cell [list $cell $site]
route_design -preserve
dict for {name pin} $original_ports {
    if {[get_property PACKAGE_PIN [get_ports $name]] ne $pin} {error "Unrelated port moved: $name"}
}
if {[llength [get_ports -quiet -filter {PACKAGE_PIN == H13}]]} {error "H13 remains assigned"}
source [file join $here validate_open_design.tcl]
puts "SERVO4_G13_ONLY_PIN_CHANGE_VERIFIED"
write_checkpoint -force [file join $output servo10_g13_verified.dcp]
write_bitstream -force [file join $output servo10_vision.bit]
puts "SERVO4_G13_BITSTREAM_READY"
close_design
