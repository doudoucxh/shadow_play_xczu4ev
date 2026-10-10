set setup [get_timing_paths -delay_type max -max_paths 1]
foreach {name expected} {clk_out1_system_clk_wiz_system_0 10.0 clk_out1_system_clk_wiz_video_0 13.333333 clk_out2_system_clk_wiz_video_0 5.333333 clk_out3_system_clk_wiz_video_0 2.666667} {
    set clock [get_clocks $name]
    if {[llength $clock]!=1 || abs([get_property PERIOD $clock]-$expected)>0.001} {error "Unexpected clock period: $name"}
}
set hold [get_timing_paths -delay_type min -max_paths 1]
if {[llength $setup] != 1 || [llength $hold] != 1} {error "Timing paths unavailable"}
set wns [get_property SLACK $setup]
set whs [get_property SLACK $hold]
puts "SERVO_TIMING WNS=$wns WHS=$whs"
if {$wns < 0 || $whs < 0} {error "Timing did not close; image must not be deployed"}
report_drc -file [file join $output verified_drc.rpt]
set errors [get_drc_violations -quiet -filter {SEVERITY == Error || SEVERITY == "Critical Warning"}]
if {[llength $errors]} {error "DRC errors: $errors"}
set pins {D14 D15 F13 G13 G14 G15 J14 E13 E14 E15}
for {set i 0} {$i < 10} {incr i} {
    set name [format {servo_pwm[%d]} $i]
    set port [get_ports $name]
    set pin [get_property PACKAGE_PIN $port]
    if {$pin != [lindex $pins $i] || [get_property IOSTANDARD $port] != "LVCMOS33"} {
        error "Unexpected servo pin/voltage constraint for $name"
    }
}
set route [report_route_status -return_string -file [file join $output verified_route.rpt]]
if {![regexp {# of routable nets[. ]*:[ ]*([0-9]+)} $route ignored total]} {error "Missing routable-net count"}
if {![regexp {# of fully routed nets[. ]*:[ ]*([0-9]+)} $route ignored routed]} {error "Missing fully-routed count"}
if {![regexp {# of nets with routing errors[. ]*:[ ]*([0-9]+)} $route ignored bad]} {error "Missing routing-error count"}
if {$total != $routed || $bad != 0} {error "Incomplete/invalid routing"}
report_timing_summary -file [file join $output verified_timing.rpt]
set bus_report [report_bus_skew -return_string -warn_on_violation]
set bus_file [open [file join $output verified_bus_skew.rpt] w]
puts $bus_file $bus_report
close $bus_file
if {[string first "VIOLATED" $bus_report]>=0} {error "Bus skew violation"}
report_io -file [file join $output verified_io.rpt]
puts "SERVO_IMAGE_DESIGN_CHECKS_PASS"
