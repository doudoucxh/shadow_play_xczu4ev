# Read-only JTAG inventory used by deployment preflight checks.
if {[catch {connect -url tcp:127.0.0.1:3121} connect_error]} {
    puts "JTAG_CONNECT_ERROR: $connect_error"
    exit 2
}
puts "JTAG_TARGETS_BEGIN"
puts [targets]
puts "JTAG_TARGETS_END"
disconnect
exit
