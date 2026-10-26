# Complete an existing candidate after BD creation; never changes the base project.
set here [file dirname [file normalize [info script]]]
set root [file normalize [file join $here ../../..]]
set output [file join $root .review_work bus_servo_tiger_20261026]
set project_dir [file join $output bus_servo]
if {[llength [get_projects -quiet]]==0} {open_project [file join $project_dir bus_servo.xpr]}
open_bd_design [get_files system.bd]
make_wrapper -files [get_files system.bd] -top
set wrapper [file join $project_dir bus_servo.gen sources_1 bd system hdl system_wrapper.v]
set f [open $wrapper r];set text [read $f];close $f
# Keep Vivado's generated full vision/DPU wrapper, changing only the three
# internal UART vectors into four IOBUF-backed physical wires.
set port_names [list tiger7_servo_bus tiger8_servo_bus tiger9_servo_bus tiger10_servo_bus]
foreach {whole pname} [regexp -all -inline -line {^  (?:input|output|inout) (?:\[[^\]]+\])? *([a-zA-Z0-9_]+);} $text] {
    if {$pname ni {bus_rx bus_tx bus_oe}} {lappend port_names $pname}
}
if {[llength $port_names] != 21} {error "Could not parse generated wrapper"}
set begin [string first "module system_wrapper" $text]
set end [string first ");" $text $begin]
set text [string replace $text $begin [expr {$end+1}] "module system_wrapper([join $port_names {, }]);"]
foreach name {bus_rx bus_tx bus_oe} {
    regsub -all [format {  (input|output) \[3:0\] *%s;\n} $name] $text "" text
}
regsub {  system system_i} $text {  inout tiger7_servo_bus;
  inout tiger8_servo_bus;
  inout tiger9_servo_bus;
  inout tiger10_servo_bus;
  IOBUF tiger7_iobuf(.IO(tiger7_servo_bus),.I(bus_tx[0]),.O(bus_rx[0]),.T(~bus_oe[0]));
  IOBUF tiger8_iobuf(.IO(tiger8_servo_bus),.I(bus_tx[1]),.O(bus_rx[1]),.T(~bus_oe[1]));
  IOBUF tiger9_iobuf(.IO(tiger9_servo_bus),.I(bus_tx[2]),.O(bus_rx[2]),.T(~bus_oe[2]));
  IOBUF tiger10_iobuf(.IO(tiger10_servo_bus),.I(bus_tx[3]),.O(bus_rx[3]),.T(~bus_oe[3]));
  system system_i} text
set top [file join $output system_bus_wrapper.v]
set f [open $top w];puts $f $text;close $f
add_files -norecurse $top
set_property top system_wrapper [current_fileset]
update_compile_order -fileset sources_1
generate_target all [get_files system.bd]
write_bd_tcl -force [file join $output bus_servo_design.tcl]
puts "TIGER_FOUR_PROJECT_READY"
close_project
