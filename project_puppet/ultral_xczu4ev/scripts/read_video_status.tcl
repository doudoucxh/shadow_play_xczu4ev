connect -url tcp:127.0.0.1:3121
targets -set -nocase -filter {name =~ "APU*"}
configparams force-mem-access 1
puts "VIDEO_VDMA_MM2S"
puts [mrd -force 0xA0000000 32]
puts "VIDEO_VDMA_S2MM"
puts [mrd -force 0xA0000030 32]
puts "VTC_CONTROL_AND_STATUS"
puts [mrd -force 0xA0030000 32]
puts "CAPTURE_BUFFER_SAMPLE"
puts [mrd -force 0x01000000 32]
puts "DISPLAY_BUFFER_SAMPLE"
puts [mrd -force 0x01800000 32]
configparams force-mem-access 0
disconnect
exit
