set here [file dirname [file normalize [info script]]]
set workspace [file normalize [file join $here ../../..]]
set out [file join $workspace .review_work usb_camera_20261010]
setws [file join $out vitis_usb]
set fsbl [file join $out vitis_usb usb_ps zynqmp_fsbl]
proc bytes {path} {
    set fd [open $path rb]; set value [read $fd]; close $fd; return $value
}
set xsa [file join $out ps_usb usb_ps.xsa]
if {![file exists [file join $fsbl fsbl_a53.elf]]} {
    platform create -name usb_ps -hw $xsa -proc psu_cortexa53_0 -os standalone
    platform generate
} elseif {[bytes $xsa] ne [bytes [file join $out vitis_usb usb_ps hw usb_ps.xsa]]} {
    error "XSA changed: use a fresh Vitis output directory; refusing a stale BSP"
}
# The generated platform already contains an FSBL-specific BSP with xilffs,
# xilsecure and xilpm. Do not build the FSBL against the generic app domain.
set header [file join $fsbl xfsbl_debug.h]
set fd [open $header r]; set text [read $fd]; close $fd
if {![string match {*#define FSBL_DEBUG_INFO*} $text]} {
    set text [string map [list "#define XFSBL_DEBUG_H" "#define XFSBL_DEBUG_H\n#define FSBL_DEBUG_INFO"] $text]
}
set fd [open $header w]; puts -nonewline $fd $text; close $fd
set vitis $::env(XILINX_VITIS)
set ::env(PATH) "[file join $vitis gnu aarch64 nt aarch64-none bin];[file join $vitis gnuwin bin];$::env(PATH)"
exec [file join $vitis gnuwin bin make.exe] -C $fsbl -j4 SHELL=CMD >@ stdout 2>@ stderr
puts "USB_FSBL_READY [file join $fsbl fsbl_a53.elf]"
exit
