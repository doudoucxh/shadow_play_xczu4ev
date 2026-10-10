set here [file dirname [file normalize [info script]]]
set output [file normalize [file join $here ../../../.review_work/servo_capture_20261008/fpga]]
set checkpoint [file join $output servo10_dpu servo10_dpu.runs impl_1 system_wrapper_physopt.dcp]
open_checkpoint $checkpoint
report_timing -delay_type max -max_paths 10 -path_type full_clock_expanded -file [file join $output critical-paths-pre-route.rpt]
foreach path [get_timing_paths -delay_type max -max_paths 5] {
    puts "CRITICAL_PATH [get_property STARTPOINT_PIN $path] -> [get_property ENDPOINT_PIN $path] SLACK=[get_property SLACK $path]"
}
close_design
