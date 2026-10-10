set here [file dirname [file normalize [info script]]]
set output [file normalize [file join $here ../../../.review_work/servo_capture_20261008/fpga]]
open_project [file join $output servo10_dpu servo10_dpu.xpr]
config_ip_cache -disable_cache
reset_run impl_1
reset_run synth_1
reset_run system_servo_pwm_0_0_synth_1
close_project
source [file join $here build_project.tcl]
