# Diagnose the first failing startup stage without requiring the PS UART.
# The PS/PL must already have been initialized by program_and_run.bat.

set script_dir   [file dirname [file normalize [info script]]]
set project_root [file normalize [file join $script_dir ..]]
if {[info exists ::env(VITIS_WORKSPACE)] && $::env(VITIS_WORKSPACE) ne ""} {
    set workspace [file normalize $::env(VITIS_WORKSPACE)]
} else {
    set workspace [file join $project_root vitis_workspace_2022_2]
}
set app_file [file join $workspace ov5640_hdmi_ultra Debug ov5640_hdmi_ultra.elf]

if {![file exists $app_file]} {
    error "Application ELF is missing: $app_file"
}

connect -url tcp:127.0.0.1:3121
targets -set -nocase -filter {name =~ "*A53*#0"}
catch {stop}
rst -processor
dow $app_file

# These addresses are taken from the linked 2022.2 ELF.  The failure blocks
# precede their xil_printf calls; pose_run_hardware_test is the success point.
array set stage_at {
    0x0000a1c0 CAMERA_ID_READ_COMPLETE
    0x000099dc CAMERA_SCCB_FAILED
    0x000099c0 VIDEO_VDMA_FAILED
    0x000099a8 HDMI_TIMING_FAILED
    0x00009a74 POSE_VDMA_FAILED
    0x00007a40 STARTUP_SUCCEEDED_POSE_LOOP_ENTERED
}

set breakpoint_ids {}
foreach address [array names stage_at] {
    lappend breakpoint_ids [bpadd -addr $address]
}

set run_result ""
set timed_out [catch {con -block -timeout 20} run_result]
catch {stop}
set pc_text ""
if {[catch {set pc_text [rrd pc]} register_error]} {
    set pc_text "PC_UNAVAILABLE: $register_error"
}
puts "STARTUP_DIAGNOSTIC_PC"
puts $pc_text
puts "STARTUP_DIAGNOSTIC_REGISTERS"
if {[catch {puts [rrd]} register_error]} {
    puts "REGISTERS_UNAVAILABLE: $register_error"
}
puts "GPIO_EMIO_BANK3_DATA_RO_DIRM_OUTEN"
puts [mrd -force 0xFF0A006C 1]
puts [mrd -force 0xFF0A02C4 2]

set pc_value -1
if {[regexp -nocase {pc:\s+([0-9a-f]+)} $pc_text -> pc_hex]} {
    scan $pc_hex %x pc_value
}

set diagnosis UNKNOWN
foreach address [array names stage_at] {
    scan $address %x address_value
    if {$pc_value == $address_value} {
        set diagnosis $stage_at($address)
        break
    }
}
if {$timed_out && $diagnosis eq "UNKNOWN"} {
    set diagnosis TIMEOUT_OR_UNEXPECTED_STOP
    puts "XSCT_RUN_RESULT: $run_result"
}
puts "STARTUP_DIAGNOSIS=$diagnosis"

foreach breakpoint_id $breakpoint_ids {
    catch {bpremove $breakpoint_id}
}
catch {con}
disconnect
exit
