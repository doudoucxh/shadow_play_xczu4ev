set script_dir [file dirname [file normalize [info script]]]
set root_dir   [file dirname $script_dir]
set proj_dir  [file join $root_dir dpu vivado_dpu]
set proj_name Shadow_ultra_dpu
set part_name xczu4ev-sfvc784-2-i

create_project -force $proj_name $proj_dir -part $part_name
set_property target_language Verilog [current_project]

set rtl_dir [file join $root_dir rtl]
add_files -norecurse [list \
  [file join $rtl_dir ov5640_capture_data.v] \
  [file join $rtl_dir pose_preprocess_axis.v] \
  [file join $rtl_dir emio_sccb_bridge.v]]
update_compile_order -fileset sources_1

add_files -fileset constrs_1 -norecurse [list \
  [file join $root_dir constraints camera_dvp.xdc] \
  [file join $root_dir constraints hdmi.xdc]]

set dvi_repo [file join $root_dir ip_repo DVI_TX]
set dpu_repo [file join $root_dir dpu DPUCZDX8G_ip_repo_VAI_v3.0]
set_property ip_repo_paths [list $dvi_repo $dpu_repo] [current_project]
update_ip_catalog

if {[get_ipdefs -all xilinx.com:ip:dpuczdx8g:4.1] eq ""} {
  error "DPUCZDX8G v4.1 was not found at $dpu_repo"
}
if {[get_ipdefs -all openedv.com:user:DVI_Transmitter:1.0] eq ""} {
  error "The official MPSoC-P4 DVI transmitter IP was not found at $dvi_repo"
}

create_bd_design system

# External camera and HDMI ports.
set cam_data   [create_bd_port -dir I -from 7 -to 0 cam_data]
set cam_pclk   [create_bd_port -dir I -type clk -freq_hz 72000000 cam_pclk]
set cam_vsync  [create_bd_port -dir I cam_vsync]
set cam_href   [create_bd_port -dir I cam_href]
set cam_rst_n  [create_bd_port -dir O -type rst cam_rst_n]
set cam_pwdn   [create_bd_port -dir O cam_pwdn]
set cam_flash  [create_bd_port -dir O cam_flash]
set cam_scl    [create_bd_port -dir IO cam_scl]
set cam_sda    [create_bd_port -dir IO cam_sda]
set tmds_clk_p [create_bd_port -dir O tmds_clk_p]
set tmds_clk_n [create_bd_port -dir O tmds_clk_n]
set tmds_dp    [create_bd_port -dir O -from 2 -to 0 tmds_data_p]
set tmds_dn    [create_bd_port -dir O -from 2 -to 0 tmds_data_n]

# MPSoC configuration follows the MPSoC-P4 tutorial: 33.333 MHz PS reference,
# UART0 on MIO42/43, four x16 Samsung DDR4 components, 64-bit/2 GiB total.
set ps [create_bd_cell -type ip -vlnv xilinx.com:ip:zynq_ultra_ps_e:* zynq_ultra_ps_e_0]
set ddr_preset [file join $::env(XILINX_VIVADO) data ip xilinx zynq_ultra_ps_e_v3_4 subpreset SUBPRESET1 DDR4_SAMSUNG_K4A8G165WB_BCRC.tcl]
source $ddr_preset
set_property -dict [apply_preset $ps] $ps
set_property -dict [list \
  CONFIG.PSU__USE__DDR_INTF_REQUESTED {1} \
  CONFIG.PSU__DDRC__COMPONENTS {Components} \
  CONFIG.PSU__DDRC__BUS_WIDTH {64 Bit} \
  CONFIG.PSU__DDRC__DRAM_WIDTH {16 Bits} \
  CONFIG.PSU__DDRC__DEVICE_CAPACITY {4096 MBits} \
  CONFIG.PSU__DDRC__BG_ADDR_COUNT {1} \
  CONFIG.PSU__DDRC__ROW_ADDR_COUNT {15} \
  CONFIG.PSU__CRF_APB__DDR_CTRL__FREQMHZ {1066} \
  CONFIG.PSU__DDRC__CL {16} \
  CONFIG.PSU__DDRC__CWL {11} \
  CONFIG.PSU__DDRC__T_RCD {16} \
  CONFIG.PSU__DDRC__T_RP {16} \
  CONFIG.PSU__UART0__PERIPHERAL__ENABLE {1} \
  CONFIG.PSU__UART0__PERIPHERAL__IO {MIO 42 .. 43} \
  CONFIG.PSU_BANK_0_IO_STANDARD {LVCMOS18} \
  CONFIG.PSU_BANK_1_IO_STANDARD {LVCMOS33} \
  CONFIG.PSU_BANK_2_IO_STANDARD {LVCMOS18} \
  CONFIG.PSU_BANK_3_IO_STANDARD {LVCMOS33} \
  CONFIG.PSU__GPIO_EMIO__PERIPHERAL__ENABLE {1} \
  CONFIG.PSU__GPIO_EMIO_WIDTH {2} \
  CONFIG.PSU__USE__M_AXI_GP0 {1} \
  CONFIG.PSU__USE__M_AXI_GP1 {1} \
  CONFIG.PSU__USE__M_AXI_GP2 {0} \
  CONFIG.PSU__MAXIGP0__DATA_WIDTH {32} \
  CONFIG.PSU__MAXIGP1__DATA_WIDTH {32} \
  CONFIG.PSU__USE__S_AXI_GP2 {1} \
  CONFIG.PSU__SAXIGP2__DATA_WIDTH {32} \
  CONFIG.PSU__USE__S_AXI_GP3 {1} \
  CONFIG.PSU__USE__S_AXI_GP4 {1} \
  CONFIG.PSU__USE__S_AXI_GP5 {1} \
  CONFIG.PSU__USE__IRQ0 {1} \
  CONFIG.PSU__FPGA_PL0_ENABLE {1} \
  CONFIG.PSU__CRL_APB__PL0_REF_CTRL__FREQMHZ {100.004023}] $ps

set rst [create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:* rst_ps_100M]
set sysclk [create_bd_cell -type ip -vlnv xilinx.com:ip:clk_wiz:* clk_wiz_system]
set_property -dict [list \
  CONFIG.PRIM_SOURCE {No_buffer} \
  CONFIG.NUM_OUT_CLKS {2} \
  CONFIG.CLKOUT1_REQUESTED_OUT_FREQ {100.000} \
  CONFIG.CLKOUT2_USED {true} \
  CONFIG.CLKOUT2_REQUESTED_OUT_FREQ {200.000} \
  CONFIG.RESET_TYPE {ACTIVE_LOW}] $sysclk
set clkgen [create_bd_cell -type ip -vlnv xilinx.com:ip:clk_wiz:* clk_wiz_video]
set_property -dict [list \
  CONFIG.PRIM_SOURCE {No_buffer} \
  CONFIG.NUM_OUT_CLKS {3} \
  CONFIG.CLKOUT1_REQUESTED_OUT_FREQ {75.000} \
  CONFIG.CLKOUT2_USED {true} \
  CONFIG.CLKOUT2_REQUESTED_OUT_FREQ {187.500} \
  CONFIG.CLKOUT3_USED {true} \
  CONFIG.CLKOUT3_REQUESTED_OUT_FREQ {375.000} \
  CONFIG.OVERRIDE_MMCM {true} \
  CONFIG.MMCM_DIVCLK_DIVIDE {1} \
  CONFIG.MMCM_CLKFBOUT_MULT_F {11.250} \
  CONFIG.MMCM_CLKOUT0_DIVIDE_F {15.000} \
  CONFIG.MMCM_CLKOUT1_DIVIDE {6} \
  CONFIG.MMCM_CLKOUT2_DIVIDE {3} \
  CONFIG.RESET_TYPE {ACTIVE_HIGH}] $clkgen

set ctrl_sc [create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect:* axi_control]
set_property -dict [list CONFIG.NUM_SI {1} CONFIG.NUM_MI {3}] $ctrl_sc
set video_mem_sc [create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect:* axi_video_memory]
set_property -dict [list CONFIG.NUM_SI {3} CONFIG.NUM_MI {1}] $video_mem_sc

set vdma [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_vdma:* axi_vdma_0]
set_property -dict [list \
  CONFIG.c_include_s2mm {1} \
  CONFIG.c_m_axis_mm2s_tdata_width {24} \
  CONFIG.c_m_axi_mm2s_data_width {64} \
  CONFIG.c_m_axi_s2mm_data_width {64} \
  CONFIG.c_mm2s_linebuffer_depth {2048} \
  CONFIG.c_s2mm_linebuffer_depth {2048} \
  CONFIG.c_mm2s_max_burst_length {64} \
  CONFIG.c_s2mm_max_burst_length {64} \
  CONFIG.c_num_fstores {3} \
  CONFIG.c_s2mm_genlock_mode {2}] $vdma

set pose_vdma [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_vdma:* axi_vdma_pose]
set_property -dict [list \
  CONFIG.c_include_mm2s {0} \
  CONFIG.c_include_s2mm {1} \
  CONFIG.c_include_s2mm_sf {1} \
  CONFIG.c_m_axi_s2mm_data_width {64} \
  CONFIG.c_num_fstores {3} \
  CONFIG.c_s2mm_linebuffer_depth {512} \
  CONFIG.c_s2mm_max_burst_length {64} \
  CONFIG.c_s2mm_sof_enable {1} \
  CONFIG.c_flush_on_fsync {1} \
  CONFIG.c_use_fsync {1} \
  CONFIG.c_use_s2mm_fsync {2}] $pose_vdma

set vin [create_bd_cell -type ip -vlnv xilinx.com:ip:v_vid_in_axi4s:* video_in]
set_property CONFIG.C_HAS_ASYNC_CLK {1} $vin
set bc [create_bd_cell -type ip -vlnv xilinx.com:ip:axis_broadcaster:* video_broadcast]
set_property -dict [list \
  CONFIG.NUM_MI {2} CONFIG.S_TDATA_NUM_BYTES {3} CONFIG.M_TDATA_NUM_BYTES {3} \
  CONFIG.HAS_TREADY {1} CONFIG.HAS_TLAST {1} \
  CONFIG.S_TUSER_WIDTH {1} CONFIG.M_TUSER_WIDTH {1}] $bc
set prep [create_bd_cell -type module -reference pose_preprocess_axis pose_preprocess]
set cap  [create_bd_cell -type module -reference ov5640_capture_data ov5640_capture]
set sccb [create_bd_cell -type module -reference emio_sccb_bridge emio_sccb_bridge]

set vout [create_bd_cell -type ip -vlnv xilinx.com:ip:v_axi4s_vid_out:* video_out]
set_property CONFIG.C_HAS_ASYNC_CLK {1} $vout
set vtc [create_bd_cell -type ip -vlnv xilinx.com:ip:v_tc:* v_tc_0]
set_property CONFIG.enable_detection {false} $vtc
set dvi [create_bd_cell -type ip -vlnv openedv.com:user:DVI_Transmitter:1.0 dvi_tx]
set dpu [create_bd_cell -type ip -vlnv xilinx.com:ip:dpuczdx8g:4.1 dpu_0]
# B4096 is the DPU configuration with 16 input and 16 output channels.  Low-DSP
# accumulation keeps the core inside the 728-DSP XCZU4EV, while 40 URAMs move
# enough DPU storage out of BRAM to leave room for the camera/video pipeline.
set_property -dict [list \
  CONFIG.ARCH {4096} \
  CONFIG.ARCH_IMG_BKGRP {2} \
  CONFIG.CONV_DSP_ACCU_ENA {0} \
  CONFIG.URAM_N_USER {40} \
  CONFIG.AXI_PROTOCOL {1} \
  CONFIG.ARCH_HP_BW {3} \
  CONFIG.S_AXI_CLK_INDEPENDENT {1} \
  CONFIG.SFM_ENA {0}] $dpu

set irq_concat [create_bd_cell -type ip -vlnv xilinx.com:ip:xlconcat:* dpu_irq_concat]
set_property CONFIG.NUM_PORTS {1} $irq_concat

set const0 [create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:* const_zero]
set_property -dict [list CONFIG.CONST_WIDTH {1} CONFIG.CONST_VAL {0}] $const0

# Camera DVP capture.
connect_bd_net [get_bd_pins $ps/emio_gpio_o] [get_bd_pins $sccb/gpio_o]
connect_bd_net [get_bd_pins $ps/emio_gpio_t] [get_bd_pins $sccb/gpio_t]
connect_bd_net [get_bd_pins $ps/emio_gpio_i] [get_bd_pins $sccb/gpio_i]
connect_bd_net $cam_scl [get_bd_pins $sccb/sccb_scl]
connect_bd_net $cam_sda [get_bd_pins $sccb/sccb_sda]
connect_bd_net $cam_data  [get_bd_pins $cap/cam_data]
connect_bd_net $cam_pclk  [get_bd_pins $cap/cam_pclk]
connect_bd_net $cam_vsync [get_bd_pins $cap/cam_vsync]
connect_bd_net $cam_href  [get_bd_pins $cap/cam_href]
connect_bd_net $cam_rst_n [get_bd_pins $cap/cam_rst_n]
connect_bd_net $cam_pwdn  [get_bd_pins $cap/cam_pwdn]
connect_bd_net $cam_flash [get_bd_pins $const0/dout]
connect_bd_net [get_bd_pins $cap/vid_clk]          [get_bd_pins $vin/vid_io_in_clk]
connect_bd_net [get_bd_pins $cap/vid_ce]           [get_bd_pins $vin/vid_io_in_ce]
connect_bd_net [get_bd_pins $cap/vid_vsync]        [get_bd_pins $vin/vid_vsync]
connect_bd_net [get_bd_pins $cap/vid_active_video] [get_bd_pins $vin/vid_active_video]
connect_bd_net [get_bd_pins $cap/vid_data]         [get_bd_pins $vin/vid_data]
connect_bd_net [get_bd_pins $const0/dout]          [get_bd_pins $vin/vid_hsync]

# Video and 256x144 pose preprocessing streams.
connect_bd_intf_net [get_bd_intf_pins $vin/video_out] [get_bd_intf_pins $bc/S_AXIS]
connect_bd_intf_net [get_bd_intf_pins $bc/M00_AXIS] [get_bd_intf_pins $vdma/S_AXIS_S2MM]
connect_bd_intf_net [get_bd_intf_pins $bc/M01_AXIS] [get_bd_intf_pins $prep/s_axis]
connect_bd_intf_net [get_bd_intf_pins $prep/m_axis] [get_bd_intf_pins $pose_vdma/S_AXIS_S2MM]
connect_bd_intf_net [get_bd_intf_pins $vdma/M_AXIS_MM2S] [get_bd_intf_pins $vout/video_in]
connect_bd_intf_net [get_bd_intf_pins $vtc/vtiming_out] [get_bd_intf_pins $vout/vtiming_in]
connect_bd_intf_net [get_bd_intf_pins $vout/vid_io_out] [get_bd_intf_pins $dvi/Video_In]
connect_bd_net [get_bd_pins $vout/vtg_ce] [get_bd_pins $vtc/gen_clken]

# Official MPSoC-P4 UltraScale+ HDMI serializer.
connect_bd_net [get_bd_pins $clkgen/clk_out1] [get_bd_pins $vout/vid_io_out_clk] [get_bd_pins $vtc/clk] [get_bd_pins $dvi/pclk]
connect_bd_net [get_bd_pins $clkgen/clk_out2] [get_bd_pins $dvi/pixel_clk_2_5x]
connect_bd_net [get_bd_pins $clkgen/clk_out3] [get_bd_pins $dvi/pixel_clk_5x]
connect_bd_net [get_bd_pins $clkgen/locked] [get_bd_pins $dvi/reset_n] [get_bd_pins $cap/rst_n]
connect_bd_net $tmds_clk_p [get_bd_pins $dvi/tmds_clk_p]
connect_bd_net $tmds_clk_n [get_bd_pins $dvi/tmds_clk_n]
connect_bd_net $tmds_dp    [get_bd_pins $dvi/tmds_data_p]
connect_bd_net $tmds_dn    [get_bd_pins $dvi/tmds_data_n]

# Control path from the A53 to VDMA, VTC and DPU registers.
connect_bd_intf_net [get_bd_intf_pins $ps/M_AXI_HPM0_FPD] [get_bd_intf_pins $ctrl_sc/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins $ctrl_sc/M00_AXI] [get_bd_intf_pins $vdma/S_AXI_LITE]
connect_bd_intf_net [get_bd_intf_pins $ctrl_sc/M01_AXI] [get_bd_intf_pins $pose_vdma/S_AXI_LITE]
connect_bd_intf_net [get_bd_intf_pins $ctrl_sc/M02_AXI] [get_bd_intf_pins $vtc/ctrl]
connect_bd_intf_net [get_bd_intf_pins $ps/M_AXI_HPM1_FPD] [get_bd_intf_pins $dpu/S_AXI]
connect_bd_net [get_bd_pins $dpu/dpu0_interrupt] [get_bd_pins $irq_concat/In0]
connect_bd_net [get_bd_pins $irq_concat/dout] [get_bd_pins $ps/pl_ps_irq0]

# Give all three DPU masters independent 128-bit HP paths.  The display/camera
# VDMAs share HP3 through a smaller 3-to-1 interconnect.  This removes the large
# 6-to-1 crossbar and prevents video traffic from serializing DPU traffic.
connect_bd_intf_net [get_bd_intf_pins $dpu/DPU0_M_AXI_INSTR] [get_bd_intf_pins $ps/S_AXI_HP0_FPD]
connect_bd_intf_net [get_bd_intf_pins $dpu/DPU0_M_AXI_DATA0] [get_bd_intf_pins $ps/S_AXI_HP1_FPD]
connect_bd_intf_net [get_bd_intf_pins $dpu/DPU0_M_AXI_DATA1] [get_bd_intf_pins $ps/S_AXI_HP2_FPD]
connect_bd_intf_net [get_bd_intf_pins $vdma/M_AXI_MM2S] [get_bd_intf_pins $video_mem_sc/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins $vdma/M_AXI_S2MM] [get_bd_intf_pins $video_mem_sc/S01_AXI]
connect_bd_intf_net [get_bd_intf_pins $pose_vdma/M_AXI_S2MM] [get_bd_intf_pins $video_mem_sc/S02_AXI]
connect_bd_intf_net [get_bd_intf_pins $video_mem_sc/M00_AXI] [get_bd_intf_pins $ps/S_AXI_HP3_FPD]

# The PS divisor produces about 96.97 MHz for a nominal 100 MHz request on this
# board. Re-clock it so AXI runs at 100 MHz and the DPU receives its required
# synchronous 2x clock at 200 MHz.
set fclk [get_bd_pins $ps/pl_clk0]
set frst [get_bd_pins $ps/pl_resetn0]
connect_bd_net $fclk [get_bd_pins $sysclk/clk_in1]
connect_bd_net $frst [get_bd_pins $sysclk/resetn] [get_bd_pins $rst/ext_reset_in]
connect_bd_net [get_bd_pins $sysclk/locked] [get_bd_pins $rst/dcm_locked]
set sys100 [get_bd_pins $sysclk/clk_out1]
set sys200 [get_bd_pins $sysclk/clk_out2]
connect_bd_net $sys100 [get_bd_pins $ps/maxihpm0_fpd_aclk] [get_bd_pins $ps/maxihpm1_fpd_aclk] \
  [get_bd_pins $ps/saxihp0_fpd_aclk] [get_bd_pins $ps/saxihp1_fpd_aclk] \
  [get_bd_pins $ps/saxihp2_fpd_aclk] [get_bd_pins $ps/saxihp3_fpd_aclk] \
  [get_bd_pins $rst/slowest_sync_clk] [get_bd_pins $ctrl_sc/aclk] [get_bd_pins $video_mem_sc/aclk] \
  [get_bd_pins $vdma/s_axi_lite_aclk] [get_bd_pins $vdma/m_axi_mm2s_aclk] \
  [get_bd_pins $vdma/m_axi_s2mm_aclk] [get_bd_pins $vdma/m_axis_mm2s_aclk] \
  [get_bd_pins $vdma/s_axis_s2mm_aclk] [get_bd_pins $pose_vdma/s_axi_lite_aclk] \
  [get_bd_pins $pose_vdma/m_axi_s2mm_aclk] [get_bd_pins $pose_vdma/s_axis_s2mm_aclk] \
  [get_bd_pins $vin/aclk] [get_bd_pins $bc/aclk] [get_bd_pins $prep/aclk] \
  [get_bd_pins $vout/aclk] [get_bd_pins $vtc/s_axi_aclk] \
  [get_bd_pins $dpu/s_axi_aclk] [get_bd_pins $dpu/m_axi_dpu_aclk] \
  [get_bd_pins $clkgen/clk_in1]
connect_bd_net $sys200 [get_bd_pins $dpu/dpu_2x_clk]

set aresetn [get_bd_pins $rst/peripheral_aresetn]
connect_bd_net $aresetn [get_bd_pins $ctrl_sc/aresetn] [get_bd_pins $video_mem_sc/aresetn] \
  [get_bd_pins $vdma/axi_resetn] [get_bd_pins $pose_vdma/axi_resetn] \
  [get_bd_pins $bc/aresetn] [get_bd_pins $prep/aresetn] \
  [get_bd_pins $vtc/s_axi_aresetn] [get_bd_pins $dpu/s_axi_aresetn] \
  [get_bd_pins $dpu/m_axi_dpu_aresetn] [get_bd_pins $dpu/dpu_2x_resetn]
connect_bd_net [get_bd_pins $rst/peripheral_reset] [get_bd_pins $clkgen/reset]

assign_bd_address
validate_bd_design
save_bd_design

make_wrapper -files [get_files system.bd] -top
add_files -norecurse [file join $proj_dir ${proj_name}.gen sources_1 bd system hdl system_wrapper.v]
set_property top system_wrapper [current_fileset]
update_compile_order -fileset sources_1

generate_target all [get_files system.bd]
export_ip_user_files -of_objects [get_files system.bd] -no_script -sync -force -quiet
write_bd_tcl -force [file join $script_dir recreate_system_dpu_bd.tcl]
close_project
puts "PASS: created $proj_dir/$proj_name.xpr"
exit
