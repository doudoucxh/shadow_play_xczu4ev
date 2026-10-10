# Read-only sampling of both VDMA engines while the application is running.
connect -url tcp:127.0.0.1:3121
targets -set -nocase -filter {name =~ "PSU*"}
configparams force-mem-access 1

puts "sample main_control main_status main_park pose_control pose_status pose_park"
for {set sample 0} {$sample < 20} {incr sample} {
    set main_control [mrd -force -value 0xA0000030]
    set main_status  [mrd -force -value 0xA0000034]
    set main_park    [mrd -force -value 0xA0000028]
    set pose_control [mrd -force -value 0xA0010030]
    set pose_status  [mrd -force -value 0xA0010034]
    set pose_park    [mrd -force -value 0xA0010028]
    puts [format "%02d 0x%08X 0x%08X 0x%08X 0x%08X 0x%08X 0x%08X" \
        $sample $main_control $main_status $main_park \
        $pose_control $pose_status $pose_park]
    after 100
}
disconnect
exit
