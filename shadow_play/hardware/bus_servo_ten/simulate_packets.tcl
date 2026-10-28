# Usage: vivado -mode batch -source simulate_packets.tcl
set here [file dirname [file normalize [info script]]]
set root [file normalize [file join $here ../../..]]
if {[llength $argv] != 0} {error "This bench verifies RTL, not a cut implementation netlist"}
set output [file join $root .review_work bus_servo_ten_packets_rtl]
create_project -force packets_rtl $output -part xczu4ev-sfvc784-2-i
add_files [list [file join $here ../bus_servo/single_wire_uart.v] [file join $here bus_servo_ten_axi.v]]
add_files -fileset sim_1 [file join $here tb_bus_servo_ten_packets.v]
set_property top tb_bus_servo_ten_packets [get_filesets sim_1]
set_property xsim.simulate.runtime all [get_filesets sim_1]
launch_simulation
set passed [get_value /tb_bus_servo_ten_packets/test_passed]
close_sim
close_project
if {$passed ne "1"} {error "Full-packet RTL test did not complete successfully"}
