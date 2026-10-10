set script_dir [file dirname [file normalize [info script]]]
set root_dir [file dirname $script_dir]
if {[info exists ::env(VITIS_WORKSPACE)] && $::env(VITIS_WORKSPACE) ne ""} {
    set workspace [file normalize $::env(VITIS_WORKSPACE)]
} else {
    # Keep the legacy workspace intact.  It contains absolute paths from the
    # original E: checkout which can stall the Vitis 2022.2 Eclipse backend.
    set workspace [file join $root_dir vitis_workspace_2022_2]
}
set xsa [file join $root_dir Shadow_ultra.xsa]
set source_dir [file join $root_dir vitis ov5640_hdmi src]

if {![file exists $xsa]} {
    error "Hardware platform is missing: $xsa. Run build_ultra_bitstream.tcl first."
}

setws $workspace
puts "Using Vitis workspace: $workspace"
if {![file exists [file join $workspace Shadow_ultra_platform platform.spr]]} {
    platform create -name Shadow_ultra_platform -hw $xsa \
        -proc psu_cortexa53_0 -os standalone
    platform active Shadow_ultra_platform
    platform generate
} else {
    platform active Shadow_ultra_platform
    platform config -updatehw $xsa
    platform generate
}

# The 2022.2 Eclipse application backend can remain alive after completing an
# app operation on some Windows hosts.  The reproducible command-line build
# only needs the generated platform/BSP, so let callers stop here explicitly.
if {[info exists ::env(VITIS_PLATFORM_ONLY)] && $::env(VITIS_PLATFORM_ONLY) ne ""} {
    puts "PASS: Vitis A53 platform and BSP generated at $workspace"
    exit
}

if {![file exists [file join $workspace ov5640_hdmi_ultra ov5640_hdmi_ultra.prj]]} {
    app create -name ov5640_hdmi_ultra -platform Shadow_ultra_platform \
        -domain standalone_domain -template {Empty Application}
}

proc copy_sources {source target} {
    file mkdir $target
    foreach entry [glob -nocomplain -directory $source *] {
        if {[file tail $entry] eq "lscript.ld"} {
            continue
        }
        set destination [file join $target [file tail $entry]]
        if {[file isdirectory $entry]} {
            copy_sources $entry $destination
        } else {
            file copy -force $entry $destination
        }
    }
}

copy_sources $source_dir [file join $workspace ov5640_hdmi_ultra src]
app build -name ov5640_hdmi_ultra
set elf [file join $workspace ov5640_hdmi_ultra Debug ov5640_hdmi_ultra.elf]
if {![file exists $elf] || [file size $elf] == 0} {
    error "Vitis did not create $elf"
}
puts "PASS: Vitis A53 application generated at $elf"
exit
