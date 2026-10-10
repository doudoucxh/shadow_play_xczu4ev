set script_dir [file dirname [file normalize [info script]]]
set project_root [file normalize [file join $script_dir ..]]
if {[info exists ::env(VITIS_WORKSPACE)] && $::env(VITIS_WORKSPACE) ne ""} {
    set workspace [file normalize $::env(VITIS_WORKSPACE)]
} else {
    set workspace [file join $project_root vitis_workspace_2022_2]
}
setws $workspace
app config -name ov5640_hdmi_ultra build-config release
app clean -name ov5640_hdmi_ultra
app build -name ov5640_hdmi_ultra
set elf [file join $workspace ov5640_hdmi_ultra Release ov5640_hdmi_ultra.elf]
if {![file exists $elf] || [file size $elf] == 0} {
    error "Release ELF was not created: $elf"
}
puts "PASS: optimized Release ELF created at $elf"
exit
