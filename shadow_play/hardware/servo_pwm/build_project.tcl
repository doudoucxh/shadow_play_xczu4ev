set here [file dirname [file normalize [info script]]]
set workspace [file normalize [file join $here ../../..]]
set output [file join $workspace .review_work servo_capture_20261008 fpga]
open_project [file join $output servo10_dpu servo10_dpu.xpr]
config_ip_cache -disable_cache
open_bd_design [get_files system.bd]
update_compile_order -fileset sources_1
generate_target all [get_files system.bd]
set_param general.maxThreads 4
launch_runs synth_1 -jobs 3
wait_on_run synth_1
if {[get_property PROGRESS [get_runs synth_1]] != "100%"} {error "PWM/vision synthesis failed"}
open_run synth_1
foreach pin {D14 D15 F13 G13 G14 G15 J14 E13 E14 E15} {
    puts "SERVO_PACKAGE_PIN $pin [get_property BANK [get_package_pins $pin]]"
}
report_io -file [file join $output servo10_io.rpt]
close_design
launch_runs impl_1 -to_step write_bitstream -jobs 3
wait_on_run impl_1
if {[get_property PROGRESS [get_runs impl_1]] != "100%"} {error "PWM/vision implementation failed"}
open_run impl_1
report_timing_summary -file [file join $output servo10_timing.rpt]
report_drc -file [file join $output servo10_drc.rpt]
source [file join $here validate_open_design.tcl]
write_hw_platform -fixed -include_bit -force -file [file join $output servo10_vision.xsa]
puts "SERVO_BITSTREAM_READY"
close_project
