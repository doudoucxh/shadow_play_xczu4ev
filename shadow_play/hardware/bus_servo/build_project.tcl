set here [file dirname [file normalize [info script]]]
set output [file normalize [file join $here ../../../.review_work/bus_servo_20261024]]
set_param general.maxThreads 4
open_project [file join $output bus_servo bus_servo.xpr]
config_ip_cache -disable_cache
launch_runs synth_1 -jobs 3
wait_on_run synth_1
if {[get_property PROGRESS [get_runs synth_1]] != "100%"} {error "Synthesis failed"}
launch_runs impl_1 -to_step route_design -jobs 3
wait_on_run impl_1
if {[get_property PROGRESS [get_runs impl_1]] != "100%"} {error "Implementation failed"}
open_run impl_1
foreach {name pin} {person_servo_bus E14 tiger_servo_bus E15} {
    set p [get_ports $name]
    if {[llength $p]!=1 || [get_property PACKAGE_PIN $p] ne $pin || [get_property DIRECTION $p] ne "INOUT" || [get_property IOSTANDARD $p] ne "LVCMOS33"} {error "Wrong bus pin: $name"}
}
if {[llength [get_ports -quiet servo_pwm*]]} {error "Legacy PWM outputs still exposed"}
foreach {name pin dir} {person_uart_tx F15 OUT person_uart_rx H13 IN tiger_uart_tx H14 OUT tiger_uart_rx L13 IN} {
    set p [get_ports $name]
    if {[get_property PACKAGE_PIN $p] ne $pin || [get_property DIRECTION $p] ne $dir} {error "Rail pins changed"}
}
set setup [get_timing_paths -delay_type max -max_paths 1]
set hold [get_timing_paths -delay_type min -max_paths 1]
if {[llength $setup]!=1 || [llength $hold]!=1} {error "Missing timing paths"}
if {[get_property SLACK $setup]<0 || [get_property SLACK $hold]<0} {error "Timing failed"}
report_timing_summary -file [file join $output timing.rpt]
report_drc -file [file join $output drc.rpt]
if {[llength [get_drc_violations -quiet -filter {SEVERITY == Error || SEVERITY == "Critical Warning"}]]} {error "DRC failed"}
set route [report_route_status -return_string -file [file join $output route.rpt]]
if {![regexp {# of routable nets[. ]*:[ ]*([0-9]+)} $route ignored total] || ![regexp {# of fully routed nets[. ]*:[ ]*([0-9]+)} $route ignored routed] || ![regexp {# of nets with routing errors[. ]*:[ ]*([0-9]+)} $route ignored bad] || $total!=$routed || $bad!=0} {error "Route failed"}
set skew [report_bus_skew -return_string -warn_on_violation]
if {[string first "VIOLATED" $skew]>=0} {error "Bus skew failed"}
set f [open [file join $output bus_skew.rpt] w];puts $f $skew;close $f
report_io -file [file join $output io.rpt]
write_checkpoint -force [file join $output bus_servo_verified.dcp]
write_bitstream -force [file join $output bus_servo.bit]
puts "BUS_SERVO_CANDIDATE_PASS WNS=[get_property SLACK $setup] WHS=[get_property SLACK $hold]"
close_project
