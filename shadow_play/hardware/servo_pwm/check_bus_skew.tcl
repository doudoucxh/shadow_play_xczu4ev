set here [file dirname [file normalize [info script]]]
set output [file normalize [file join $here ../../../.review_work/servo_capture_20261008/fpga]]
set_param general.maxThreads 4
open_checkpoint [file join $output servo10_verified.dcp]
set report [report_bus_skew -return_string -warn_on_violation]
set stream [open [file join $output verified_bus_skew.rpt] w]
puts $stream $report
close $stream
if {[string first "VIOLATED" $report]>=0} {error "Bus skew violation; do not load image"}
puts "SERVO_BUS_SKEW_CHECK_PASS"
close_design
