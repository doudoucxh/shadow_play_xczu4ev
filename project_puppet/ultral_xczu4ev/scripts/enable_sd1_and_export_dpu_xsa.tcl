set script_dir [file dirname [file normalize [info script]]]
set root_dir [file normalize [file join $script_dir ..]]
set dpu_root [file join $root_dir dpu]
set project_file [file join $dpu_root vivado_dpu Shadow_ultra_dpu.xpr]
set output_file [file join $dpu_root build Shadow_ultra_dpu_b4096_sd1.xsa]

open_project $project_file
open_bd_design [file join $dpu_root vivado_dpu Shadow_ultra_dpu.srcs sources_1 bd system system.bd]
set ps [get_bd_cells zynq_ultra_ps_e_0]

# MPSoC-P4 micro-SD socket: SD1 data/cmd/clock on MIO 46..51,
# active-low card detect on MIO 45.  These values mirror the vendor's
# XCZU4EV embedded-Linux base design.
set sd1_cfg [list \
    CONFIG.PSU_SD1_INTERNAL_BUS_WIDTH {4} \
    CONFIG.PSU__CRL_APB__SDIO1_REF_CTRL__FREQMHZ {200} \
    CONFIG.PSU__CRL_APB__SDIO1_REF_CTRL__SRCSEL {IOPLL} \
    CONFIG.PSU__SD1_COHERENCY {0} \
    CONFIG.PSU__SD1_ROUTE_THROUGH_FPD {0} \
    CONFIG.PSU__SD1__DATA_TRANSFER_MODE {4Bit} \
    CONFIG.PSU__SD1__GRP_CD__ENABLE {1} \
    CONFIG.PSU__SD1__GRP_CD__IO {MIO 45} \
    CONFIG.PSU__SD1__GRP_POW__ENABLE {0} \
    CONFIG.PSU__SD1__GRP_WP__ENABLE {0} \
    CONFIG.PSU__SD1__PERIPHERAL__ENABLE {1} \
    CONFIG.PSU__SD1__PERIPHERAL__IO {MIO 46 .. 51} \
    CONFIG.PSU__SD1__RESET__ENABLE {0} \
    CONFIG.PSU__SD1__SLOT_TYPE {SD 2.0}]

foreach {property value} $sd1_cfg {
    if {[lsearch -exact [list_property $ps] $property] < 0} {
        error "Missing PS property: $property"
    }
}

# Apply the complete SD1 configuration atomically.  Enabling the peripheral
# separately would momentarily select its MIO 39..51 default and collide with
# UART0 on MIO 42..43 before the intended MIO 46..51 value is applied.
set_property -dict $sd1_cfg $ps
foreach {property value} $sd1_cfg {
    puts "SET $property = [get_property $property $ps]"
}

validate_bd_design
save_bd_design
generate_target all [get_files system.bd]
set_property top system_wrapper [current_fileset]
update_compile_order -fileset sources_1
write_hw_platform -fixed -force $output_file

puts "PASS: SD1-enabled XSA generated: $output_file"
exit 0
