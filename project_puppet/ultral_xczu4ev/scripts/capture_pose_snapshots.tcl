# Capture atomic PoseHardwareResult v7 snapshots and the matching raw buffers.
# Usage: xsdb capture_pose_snapshots.tcl ?output_dir? ?count?
proc s32 {value} {
    set unsigned [expr {wide($value) & 0xFFFFFFFF}]
    return [expr {$unsigned >= 0x80000000 ? $unsigned - 0x100000000 : $unsigned}]
}

proc valid_header {words} {
    if {[llength $words] != 56} { return 0 }
    set magic [expr {wide([lindex $words 0]) & 0xFFFFFFFF}]
    set version [lindex $words 1]
    set bytes [lindex $words 2]
    set sequence [lindex $words 3]
    set sequence_end [lindex $words 55]
    return [expr {$magic == 0x504F5345 && $version == 7 && $bytes == 224 &&
                  ($sequence & 1) == 0 && $sequence == $sequence_end}]
}

set script_dir [file dirname [file normalize [info script]]]
set project_root [file normalize [file join $script_dir .. ..]]
set output_dir [expr {$argc >= 1 ? [file normalize [lindex $argv 0]] : [file join $project_root deploy board_snapshots]}]
set requested [expr {$argc >= 2 ? int([lindex $argv 1]) : 1}]
file mkdir $output_dir
set existing [llength [glob -nocomplain -directory $output_dir sample_*.json]]

connect -url tcp:127.0.0.1:3121
targets -set -nocase -filter {name =~ "PSU*"}
configparams force-mem-access 1
set captured 0
set previous_sequence -1
while {$captured < $requested} {
    set before [mrd -force -value 0x02200000 56]
    if {![valid_header $before] || [lindex $before 3] == $previous_sequence} {
        after 100
        continue
    }
    set sequence [lindex $before 3]
    set stem [format "sample_%06d" [expr {$existing + $captured + 1}]]
    set input_file [file join $output_dir "$stem.input.bin"]
    set heatmap_file [file join $output_dir "$stem.heatmap.bin"]
    mrd -force -bin -file $input_file [lindex $before 19] [expr {[lindex $before 20] / 4}]
    mrd -force -bin -file $heatmap_file [lindex $before 21] [expr {[lindex $before 22] / 4}]
    set after_words [mrd -force -value 0x02200000 56]
    if {![valid_header $after_words] || [lindex $after_words 3] != $sequence} {
        file delete -force $input_file $heatmap_file
        puts "RETRY snapshot changed while buffers were read"
        continue
    }

    set sha ""
    for {set index 4} {$index < 12} {incr index} {
        append sha [format %08x [expr {wide([lindex $after_words $index]) & 0xFFFFFFFF}]]
    }
    set px {}
    set py {}
    set logits {}
    for {set point 0} {$point < 9} {incr point} {
        set base [expr {28 + $point * 3}]
        lappend px [s32 [lindex $after_words $base]]
        lappend py [s32 [lindex $after_words [expr {$base + 1}]]]
        lappend logits [s32 [lindex $after_words [expr {$base + 2}]]]
    }
    set metadata_file [file join $output_dir "$stem.json"]
    set stream [open $metadata_file w]
    puts $stream "{"
    puts $stream {  "schema_version": 1,}
    puts $stream [format {  "snapshot_sequence": %d,} $sequence]
    puts $stream [format {  "model_sha256": "%s",} $sha]
    puts $stream [format {  "frame_counter": %d,} [lindex $after_words 12]]
    puts $stream [format {  "frame_period_us": %d,} [lindex $after_words 14]]
    puts $stream [format {  "backend_pl": %d,} [lindex $after_words 15]]
    puts $stream [format {  "completed_layers": %d,} [lindex $after_words 16]]
    puts $stream [format {  "failed_layer": %d,} [lindex $after_words 17]]
    puts $stream [format {  "inference_us": %d,} [lindex $after_words 18]]
    puts $stream [format {  "roi": [%d, %d, %d, %d],} [s32 [lindex $after_words 23]] [s32 [lindex $after_words 24]] [s32 [lindex $after_words 25]] [s32 [lindex $after_words 26]]]
    puts $stream [format {  "points_x": [%s],} [join $px ", "]]
    puts $stream [format {  "points_y": [%s],} [join $py ", "]]
    puts $stream [format {  "logit_milli": [%s]} [join $logits ", "]]
    puts $stream "}"
    close $stream
    set previous_sequence $sequence
    incr captured
    puts "CAPTURED $stem snapshot=$sequence model_sha256=$sha"
}
disconnect
puts "PASS captured=$captured output=$output_dir"
exit
