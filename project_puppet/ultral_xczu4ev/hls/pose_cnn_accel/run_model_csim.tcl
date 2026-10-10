set script_dir [file dirname [file normalize [info script]]]
set project_root [file normalize [file join $script_dir .. .. ..]]
set input_file [expr {[info exists ::env(POSE_CSIM_INPUT)] ?
    [file normalize $::env(POSE_CSIM_INPUT)] :
    [file join $project_root deploy csim input_bgr.bin]}]
set output_file [expr {[info exists ::env(POSE_CSIM_OUTPUT)] ?
    [file normalize $::env(POSE_CSIM_OUTPUT)] :
    [file join $project_root deploy csim hls_heatmap.bin]}]
if {![file exists $input_file]} {
    error "C-sim input is missing: $input_file"
}
cd $script_dir
open_project -reset model_csim_build
set_top pose_cnn_accel
add_files [file join $script_dir pose_cnn_accel.cpp]
add_files [file join $script_dir pose_cnn_accel.h]
add_files -tb [file join $script_dir tb_pose_model.cpp]
open_solution -reset solution1 -flow_target vivado
set_part {xczu4ev-sfvc784-2-i}
create_clock -period 5 -name default
csim_design -clean -argv [list $input_file $output_file]
exit
