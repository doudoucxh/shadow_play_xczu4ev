set workspace [file normalize D:/vitis_sd1_fsbl_2022_2]
set xsa [file normalize D:/xilinx_project/ZYNQ_project/project_puppet/project_puppet/ultral_xczu4ev/dpu/build/Shadow_ultra_dpu_b4096_sd1.xsa]

if {![file exists $xsa]} {
    error "Missing SD1-enabled XSA: $xsa"
}

setws $workspace
platform create -name Shadow_sd1_platform -hw $xsa \
    -proc psu_cortexa53_0 -os standalone
platform active Shadow_sd1_platform
platform generate

puts "PASS: generated SD1 FSBL platform at $workspace"
exit
