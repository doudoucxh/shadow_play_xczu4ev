# Read-only live diagnostics for PoseHardwareResult v7.
proc s32 {value} {
    set unsigned [expr {wide($value) & 0xFFFFFFFF}]
    return [expr {$unsigned >= 0x80000000 ? $unsigned - 0x100000000 : $unsigned}]
}

connect -url tcp:127.0.0.1:3121
targets -set -nocase -filter {name =~ "*A53*#0"}
configparams force-mem-access 1
set words [mrd -force -value 0x02200000 56]
set magic [lindex $words 0]
set version [lindex $words 1]
set sequence [lindex $words 3]
set sequence_end [lindex $words 55]
set sha ""
for {set index 4} {$index < 12} {incr index} {
    append sha [format %08x [expr {wide([lindex $words $index]) & 0xFFFFFFFF}]]
}
puts [format "POSE_RESULT magic=0x%08X version=%d bytes=%d snapshot=%d/%d" $magic $version [lindex $words 2] $sequence $sequence_end]
puts "model_sha256=$sha"
puts [format "frame=%d backend_pl=%d layers=%d failed_layer=%d frame_period_us=%d inference_us=%d" \
    [lindex $words 12] [lindex $words 15] [lindex $words 16] [lindex $words 17] [lindex $words 14] [lindex $words 18]]
puts [format "input=0x%08X/%d heatmap=0x%08X/%d roi=%d,%d,%d,%d motion=%d" \
    [lindex $words 19] [lindex $words 20] [lindex $words 21] [lindex $words 22] \
    [s32 [lindex $words 23]] [s32 [lindex $words 24]] [s32 [lindex $words 25]] [s32 [lindex $words 26]] [lindex $words 27]]
puts "POSE_CNN_STATUS @ 0x02200100"
puts [mrd -force 0x02200100 6]
puts "VDMA/HLS AXI probes"
puts [mrd -force 0xA0000000 4]
puts [mrd -force 0xA0020000 4]
disconnect
exit
