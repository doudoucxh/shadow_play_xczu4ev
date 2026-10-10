# Capture 256x144 BGR network inputs from either legacy v6 or atomic v7 firmware.
# Usage: xsdb capture_calibration_inputs.tcl ?output_dir? ?count?
set script_dir [file dirname [file normalize [info script]]]
set project_root [file normalize [file join $script_dir .. ..]]
set output_dir [expr {$argc >= 1 ? [file normalize [lindex $argv 0]] : [file join $project_root deploy board_calibration]}]
set requested [expr {$argc >= 2 ? int([lindex $argv 1]) : 200}]
file mkdir $output_dir
set existing [llength [glob -nocomplain -directory $output_dir calibration_*.input.bin]]

connect -url tcp:127.0.0.1:3121
targets -set -nocase -filter {name =~ "PSU*"}
configparams force-mem-access 1
set captured 0
set previous_token -1
while {$captured < $requested} {
    set before [mrd -force -value 0x02200000 56]
    set magic [expr {wide([lindex $before 0]) & 0xFFFFFFFF}]
    set version [lindex $before 1]
    if {$magic != 0x504F5345} {
        after 100
        continue
    }
    if {$version >= 7} {
        set token [lindex $before 3]
        set token_end [lindex $before 55]
        set address [lindex $before 19]
        set bytes [lindex $before 20]
        set ready [expr {($token & 1) == 0 && $token == $token_end}]
    } elseif {$version == 6} {
        set token [lindex $before 6]
        set address [lindex $before 4]
        set bytes 110592
        set ready [expr {($token % 30) == 1}]
    } else {
        error "Unsupported PoseHardwareResult version: $version"
    }
    if {!$ready || $token == $previous_token} {
        after 100
        continue
    }
    set stem [format "calibration_%06d.input.bin" [expr {$existing + $captured + 1}]]
    set output_file [file join $output_dir $stem]
    mrd -force -bin -file $output_file $address [expr {$bytes / 4}]
    set after_words [mrd -force -value 0x02200000 56]
    set after_token [expr {$version >= 7 ? [lindex $after_words 3] : [lindex $after_words 6]}]
    if {$after_token != $token} {
        file delete -force $output_file
        puts "RETRY input snapshot changed while being read"
        continue
    }
    set previous_token $token
    incr captured
    puts "CALIBRATION_CAPTURED $captured/$requested firmware_v=$version token=$token file=$stem"
}
disconnect
puts "PASS captured=$captured output=$output_dir"
exit
