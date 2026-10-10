# Briefly halt Cortex-A53 #0 for a read-only program-counter/backtrace check,
# then always resume it before disconnecting.
connect -url tcp:127.0.0.1:3121
targets -set -nocase -filter {name =~ "*A53*#0"}
catch {stop}
after 100
puts "A53_PC"
if {[catch {puts [rrd pc]} register_error]} { puts "PC_UNAVAILABLE: $register_error" }
puts "A53_LR"
if {[catch {puts [rrd x30]} register_error]} { puts "LR_UNAVAILABLE: $register_error" }
puts "A53_SP"
if {[catch {puts [rrd sp]} register_error]} { puts "SP_UNAVAILABLE: $register_error" }
puts "A53_BACKTRACE"
if {[catch {puts [bt]} backtrace_error]} {
    puts "BACKTRACE_UNAVAILABLE: $backtrace_error"
}
puts "DDR_RESULT_HEADER"
puts [mrd -force 0x02200000 8]
con
disconnect
exit
