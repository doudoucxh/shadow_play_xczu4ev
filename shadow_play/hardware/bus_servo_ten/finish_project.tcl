# Complete an existing candidate after BD creation; never changes the base project.
set here [file dirname [file normalize [info script]]]
set root [file normalize [file join $here ../../..]]
set output [file join $root .review_work bus_servo_ten_20261028]
set project_dir [file join $output bus_servo]
if {[llength [get_projects -quiet]]==0} {open_project [file join $project_dir bus_servo.xpr]}
open_bd_design [get_files system.bd]
make_wrapper -files [get_files system.bd] -top
set wrapper [file join $project_dir bus_servo.gen sources_1 bd system hdl system_wrapper.v]
set f [open $wrapper r];set text [read $f];close $f
# Keep Vivado's generated full vision/DPU wrapper, changing only the three
# internal UART vectors into ten IOBUF-backed independent physical wires.
set port_names [list servo1_servo_bus servo2_servo_bus servo3_servo_bus servo4_servo_bus servo5_servo_bus servo6_servo_bus servo7_servo_bus servo8_servo_bus servo9_servo_bus servo10_servo_bus]
foreach {whole pname} [regexp -all -inline -line {^  (?:input|output|inout) (?:\[[^\]]+\])? *([a-zA-Z0-9_]+);} $text] {
    if {$pname ni {bus_rx bus_tx bus_oe}} {lappend port_names $pname}
}
if {[llength $port_names] != 27} {error "Could not parse generated wrapper"}
set begin [string first "module system_wrapper" $text]
set end [string first ");" $text $begin]
set text [string replace $text $begin [expr {$end+1}] "module system_wrapper([join $port_names {, }]);"]
foreach name {bus_rx bus_tx bus_oe} {
    regsub -all [format {  (input|output) \[9:0\] *%s;\n} $name] $text "" text
}
regsub {  system system_i} $text {  inout servo1_servo_bus;
  inout servo2_servo_bus;
  inout servo3_servo_bus;
  inout servo4_servo_bus;
  inout servo5_servo_bus;
  inout servo6_servo_bus;
  inout servo7_servo_bus;
  inout servo8_servo_bus;
  inout servo9_servo_bus;
  inout servo10_servo_bus;
  IOBUF servo1_iobuf(.IO(servo1_servo_bus),.I(bus_tx[0]),.O(bus_rx[0]),.T(~bus_oe[0]));
  IOBUF servo2_iobuf(.IO(servo2_servo_bus),.I(bus_tx[1]),.O(bus_rx[1]),.T(~bus_oe[1]));
  IOBUF servo3_iobuf(.IO(servo3_servo_bus),.I(bus_tx[2]),.O(bus_rx[2]),.T(~bus_oe[2]));
  IOBUF servo4_iobuf(.IO(servo4_servo_bus),.I(bus_tx[3]),.O(bus_rx[3]),.T(~bus_oe[3]));
  IOBUF servo5_iobuf(.IO(servo5_servo_bus),.I(bus_tx[4]),.O(bus_rx[4]),.T(~bus_oe[4]));
  IOBUF servo6_iobuf(.IO(servo6_servo_bus),.I(bus_tx[5]),.O(bus_rx[5]),.T(~bus_oe[5]));
  IOBUF servo7_iobuf(.IO(servo7_servo_bus),.I(bus_tx[6]),.O(bus_rx[6]),.T(~bus_oe[6]));
  IOBUF servo8_iobuf(.IO(servo8_servo_bus),.I(bus_tx[7]),.O(bus_rx[7]),.T(~bus_oe[7]));
  IOBUF servo9_iobuf(.IO(servo9_servo_bus),.I(bus_tx[8]),.O(bus_rx[8]),.T(~bus_oe[8]));
  IOBUF servo10_iobuf(.IO(servo10_servo_bus),.I(bus_tx[9]),.O(bus_rx[9]),.T(~bus_oe[9]));
  system system_i} text
set top [file join $output system_bus_wrapper.v]
set f [open $top w];puts $f $text;close $f
add_files -norecurse $top
set_property top system_wrapper [current_fileset]
update_compile_order -fileset sources_1
generate_target all [get_files system.bd]
write_bd_tcl -force [file join $output bus_servo_design.tcl]
puts "TEN_PORT_PROJECT_READY"
close_project
