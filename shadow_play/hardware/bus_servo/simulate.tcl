set here [file dirname [file normalize [info script]]]
set output [file normalize [file join $here ../../../.review_work/bus_servo_sim]]
file mkdir $output
create_project -force bus_servo_sim $output -part xczu4ev-sfvc784-2-i
add_files [list [file join $here single_wire_uart.v] [file join $here bus_servo_axi.v]]
add_files -fileset sim_1 [file join $here tb_bus_servo_axi.v]
set_property top tb_bus_servo_axi [get_filesets sim_1]
set_property xsim.simulate.runtime all [get_filesets sim_1]
launch_simulation
close_sim
close_project
