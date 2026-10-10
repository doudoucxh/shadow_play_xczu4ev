set script_dir [file dirname [file normalize [info script]]]
cd $script_dir

open_project -reset build_csim
set_top pose_cnn_accel
add_files [file join $script_dir pose_cnn_accel.cpp]
add_files [file join $script_dir pose_cnn_accel.h]
add_files -tb [file join $script_dir tb_pose_cnn_accel.cpp]
open_solution -reset solution1 -flow_target vivado
set_part {xczu4ev-sfvc784-2-i}
create_clock -period 5 -name default
config_compile -pipeline_loops 0
csim_design -clean
exit
