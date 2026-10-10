set script_dir [file dirname [file normalize [info script]]]
set project_root [file dirname $script_dir]
open_project [file join $project_root vivado Shadow_ultra.xpr]
set matches [get_ipdefs -all -filter {VLNV =~ "*DPU*" || NAME =~ "*DPU*"}]
if {[llength $matches] == 0} {
    puts "DPU_IP_NOT_FOUND"
} else {
    puts "DPU_IP_FOUND"
    foreach item $matches {
        puts [get_property VLNV $item]
    }
}
exit
