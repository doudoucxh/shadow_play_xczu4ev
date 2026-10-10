set script_dir [file dirname [file normalize [info script]]]
set root_dir [file dirname $script_dir]
if {[info exists ::env(DPU_BRINGUP_WORKSPACE)] && $::env(DPU_BRINGUP_WORKSPACE) ne ""} {
    set workspace [file normalize $::env(DPU_BRINGUP_WORKSPACE)]
} else {
    # Vitis 2022.2 BSP generators still hit Windows path-length limits when a
    # fresh platform is created under the deeply nested source checkout.
    set workspace [file normalize D:/vitis_dpu_bringup_2022_2]
}
set project_root [file dirname $root_dir]
set xsa [file join $project_root deploy dpu_arm_chain hardware Shadow_ultra_dpu_b4096.xsa]
set source_dir [file join $root_dir vitis ov5640_hdmi_dpu_bringup src]

if {![file exists $xsa]} {
    error "DPU hardware platform is missing: $xsa"
}
if {![file exists [file join $source_dir main.c]]} {
    error "DPU bring-up sources are missing: $source_dir"
}

setws $workspace
puts "Using Vitis workspace: $workspace"
puts "Using DPU XSA: $xsa"

if {![file exists [file join $workspace Shadow_dpu_platform platform.spr]]} {
    platform create -name Shadow_dpu_platform -hw $xsa \
        -proc psu_cortexa53_0 -os standalone
} else {
    platform active Shadow_dpu_platform
    platform config -updatehw $xsa
}
platform active Shadow_dpu_platform
platform generate

if {[info exists ::env(VITIS_PLATFORM_ONLY)] && $::env(VITIS_PLATFORM_ONLY) ne ""} {
    puts "PASS: DPU bring-up platform generated at $workspace"
    exit
}

if {![file exists [file join $workspace ov5640_hdmi_dpu_bringup]]} {
    app create -name ov5640_hdmi_dpu_bringup -platform Shadow_dpu_platform \
        -domain standalone_domain -template {Empty Application}
}

proc copy_tree {source target} {
    file mkdir $target
    foreach entry [glob -nocomplain -directory $source *] {
        set destination [file join $target [file tail $entry]]
        if {[file isdirectory $entry]} {
            copy_tree $entry $destination
        } else {
            file copy -force $entry $destination
        }
    }
}

copy_tree $source_dir [file join $workspace ov5640_hdmi_dpu_bringup src]
app build -name ov5640_hdmi_dpu_bringup

set elf [file join $workspace ov5640_hdmi_dpu_bringup Debug ov5640_hdmi_dpu_bringup.elf]
if {![file exists $elf] || [file size $elf] == 0} {
    error "Vitis did not create $elf"
}
puts "PASS: DPU camera/HDMI bring-up ELF generated at $elf"
exit
