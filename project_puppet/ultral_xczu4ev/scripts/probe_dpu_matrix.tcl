# Report DPUCZDX8G v4.1 resource counters for candidate configurations.
# This project is isolated from the camera/HDMI implementation.
set script_dir [file dirname [file normalize [info script]]]
set root_dir   [file normalize [file join $script_dir ..]]
set probe_dir  [file join $root_dir dpu matrix_project]
set ip_repo    [file join $root_dir dpu DPUCZDX8G_ip_repo_VAI_v3.0]

create_project -force dpu_matrix $probe_dir -part xczu4ev-sfvc784-2-i
set_property ip_repo_paths [list $ip_repo] [current_project]
update_ip_catalog
create_bd_design dpu_matrix_bd
create_bd_cell -type ip -vlnv xilinx.com:ip:dpuczdx8g:4.1 dpu_0
set dpu [get_bd_cells dpu_0]

proc report_cfg {dpu arch ram dsp uram} {
  set_property -dict [list \
    CONFIG.ARCH $arch \
    CONFIG.ARCH_IMG_BKGRP $ram \
    CONFIG.CONV_DSP_ACCU_ENA $dsp \
    CONFIG.URAM_N_USER $uram] $dpu
  set actual_arch [get_property CONFIG.ARCH $dpu]
  set icp         [get_property CONFIG.ARCH_ICP $dpu]
  set ocp         [get_property CONFIG.ARCH_OCP $dpu]
  set bram        [get_property CONFIG.SUM_BRAM_N $dpu]
  set uram_n      [get_property CONFIG.SUM_URAM_N $dpu]
  set dsp_n       [get_property CONFIG.SUM_DSP_NUM $dpu]
  puts "DPU_MATRIX arch=B${actual_arch} icp=${icp} ocp=${ocp} ram=${ram} dsp_mode=${dsp} uram_req=${uram} DSP=${dsp_n} BRAM=${bram} URAM=${uram_n}"
}

foreach arch {512 800 1024 1152 1600 2304 3136 4096} {
  report_cfg $dpu $arch 2 0 0
  report_cfg $dpu $arch 2 1 0
}

foreach uram {8 16 24 32 40 48} {
  report_cfg $dpu 4096 2 0 $uram
}

save_bd_design
close_project
exit 0
