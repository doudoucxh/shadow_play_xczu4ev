
################################################################
# This is a generated script based on design: system
#
# Though there are limitations about the generated script,
# the main purpose of this utility is to make learning
# IP Integrator Tcl commands easier.
################################################################

namespace eval _tcl {
proc get_script_folder {} {
   set script_path [file normalize [info script]]
   set script_folder [file dirname $script_path]
   return $script_folder
}
}
variable script_folder
set script_folder [_tcl::get_script_folder]

################################################################
# Check if script is running in correct Vivado version.
################################################################
set scripts_vivado_version 2022.2
set current_vivado_version [version -short]

if { [string first $scripts_vivado_version $current_vivado_version] == -1 } {
   puts ""
   catch {common::send_gid_msg -ssname BD::TCL -id 2041 -severity "ERROR" "This script was generated using Vivado <$scripts_vivado_version> and is being run in <$current_vivado_version> of Vivado. Please run the script in Vivado <$scripts_vivado_version> then open the design in Vivado <$current_vivado_version>. Upgrade the design by running \"Tools => Report => Report IP Status...\", then run write_bd_tcl to create an updated script."}

   return 1
}

################################################################
# START
################################################################

# To test this script, run the following commands from Vivado Tcl console:
# source system_script.tcl


# The design that will be created by this Tcl script contains the following 
# module references:
# emio_sccb_bridge, ov5640_capture_data, pose_preprocess_axis

# Please add the sources of those modules before sourcing this Tcl script.

# If there is no project opened, this script will create a
# project, but make sure you do not have an existing project
# <./myproj/project_1.xpr> in the current working folder.

set list_projs [get_projects -quiet]
if { $list_projs eq "" } {
   create_project project_1 myproj -part xczu4ev-sfvc784-2-i
}


# CHANGE DESIGN NAME HERE
variable design_name
set design_name system

# If you do not already have an existing IP Integrator design open,
# you can create a design using the following command:
#    create_bd_design $design_name

# Creating design if needed
set errMsg ""
set nRet 0

set cur_design [current_bd_design -quiet]
set list_cells [get_bd_cells -quiet]

if { ${design_name} eq "" } {
   # USE CASES:
   #    1) Design_name not set

   set errMsg "Please set the variable <design_name> to a non-empty value."
   set nRet 1

} elseif { ${cur_design} ne "" && ${list_cells} eq "" } {
   # USE CASES:
   #    2): Current design opened AND is empty AND names same.
   #    3): Current design opened AND is empty AND names diff; design_name NOT in project.
   #    4): Current design opened AND is empty AND names diff; design_name exists in project.

   if { $cur_design ne $design_name } {
      common::send_gid_msg -ssname BD::TCL -id 2001 -severity "INFO" "Changing value of <design_name> from <$design_name> to <$cur_design> since current design is empty."
      set design_name [get_property NAME $cur_design]
   }
   common::send_gid_msg -ssname BD::TCL -id 2002 -severity "INFO" "Constructing design in IPI design <$cur_design>..."

} elseif { ${cur_design} ne "" && $list_cells ne "" && $cur_design eq $design_name } {
   # USE CASES:
   #    5) Current design opened AND has components AND same names.

   set errMsg "Design <$design_name> already exists in your project, please set the variable <design_name> to another value."
   set nRet 1
} elseif { [get_files -quiet ${design_name}.bd] ne "" } {
   # USE CASES: 
   #    6) Current opened design, has components, but diff names, design_name exists in project.
   #    7) No opened design, design_name exists in project.

   set errMsg "Design <$design_name> already exists in your project, please set the variable <design_name> to another value."
   set nRet 2

} else {
   # USE CASES:
   #    8) No opened design, design_name not in project.
   #    9) Current opened design, has components, but diff names, design_name not in project.

   common::send_gid_msg -ssname BD::TCL -id 2003 -severity "INFO" "Currently there is no design <$design_name> in project, so creating one..."

   create_bd_design $design_name

   common::send_gid_msg -ssname BD::TCL -id 2004 -severity "INFO" "Making design <$design_name> as current_bd_design."
   current_bd_design $design_name

}

common::send_gid_msg -ssname BD::TCL -id 2005 -severity "INFO" "Currently the variable <design_name> is equal to \"$design_name\"."

if { $nRet != 0 } {
   catch {common::send_gid_msg -ssname BD::TCL -id 2006 -severity "ERROR" $errMsg}
   return $nRet
}

set bCheckIPsPassed 1
##################################################################
# CHECK IPs
##################################################################
set bCheckIPs 1
if { $bCheckIPs == 1 } {
   set list_check_ips "\ 
xilinx.com:ip:smartconnect:1.0\
xilinx.com:ip:axi_vdma:6.3\
xilinx.com:ip:clk_wiz:6.0\
xilinx.com:ip:xlconstant:1.1\
xilinx.com:ip:dpuczdx8g:4.1\
xilinx.com:ip:xlconcat:2.1\
openedv.com:user:DVI_Transmitter:1.0\
xilinx.com:ip:proc_sys_reset:5.0\
xilinx.com:ip:v_tc:6.2\
xilinx.com:ip:axis_broadcaster:1.1\
xilinx.com:ip:v_vid_in_axi4s:5.0\
xilinx.com:ip:v_axi4s_vid_out:4.0\
xilinx.com:ip:zynq_ultra_ps_e:3.4\
"

   set list_ips_missing ""
   common::send_gid_msg -ssname BD::TCL -id 2011 -severity "INFO" "Checking if the following IPs exist in the project's IP catalog: $list_check_ips ."

   foreach ip_vlnv $list_check_ips {
      set ip_obj [get_ipdefs -all $ip_vlnv]
      if { $ip_obj eq "" } {
         lappend list_ips_missing $ip_vlnv
      }
   }

   if { $list_ips_missing ne "" } {
      catch {common::send_gid_msg -ssname BD::TCL -id 2012 -severity "ERROR" "The following IPs are not found in the IP Catalog:\n  $list_ips_missing\n\nResolution: Please add the repository containing the IP(s) to the project." }
      set bCheckIPsPassed 0
   }

}

##################################################################
# CHECK Modules
##################################################################
set bCheckModules 1
if { $bCheckModules == 1 } {
   set list_check_mods "\ 
emio_sccb_bridge\
ov5640_capture_data\
pose_preprocess_axis\
"

   set list_mods_missing ""
   common::send_gid_msg -ssname BD::TCL -id 2020 -severity "INFO" "Checking if the following modules exist in the project's sources: $list_check_mods ."

   foreach mod_vlnv $list_check_mods {
      if { [can_resolve_reference $mod_vlnv] == 0 } {
         lappend list_mods_missing $mod_vlnv
      }
   }

   if { $list_mods_missing ne "" } {
      catch {common::send_gid_msg -ssname BD::TCL -id 2021 -severity "ERROR" "The following module(s) are not found in the project: $list_mods_missing" }
      common::send_gid_msg -ssname BD::TCL -id 2022 -severity "INFO" "Please add source files for the missing module(s) above."
      set bCheckIPsPassed 0
   }
}

if { $bCheckIPsPassed != 1 } {
  common::send_gid_msg -ssname BD::TCL -id 2023 -severity "WARNING" "Will not continue with creation of design due to the error(s) above."
  return 3
}

##################################################################
# DESIGN PROCs
##################################################################



# Procedure to create entire design; Provide argument to make
# procedure reusable. If parentCell is "", will use root.
proc create_root_design { parentCell } {

  variable script_folder
  variable design_name

  if { $parentCell eq "" } {
     set parentCell [get_bd_cells /]
  }

  # Get object for parentCell
  set parentObj [get_bd_cells $parentCell]
  if { $parentObj == "" } {
     catch {common::send_gid_msg -ssname BD::TCL -id 2090 -severity "ERROR" "Unable to find parent cell <$parentCell>!"}
     return
  }

  # Make sure parentObj is hier blk
  set parentType [get_property TYPE $parentObj]
  if { $parentType ne "hier" } {
     catch {common::send_gid_msg -ssname BD::TCL -id 2091 -severity "ERROR" "Parent <$parentObj> has TYPE = <$parentType>. Expected to be <hier>."}
     return
  }

  # Save current instance; Restore later
  set oldCurInst [current_bd_instance .]

  # Set parent object as current
  current_bd_instance $parentObj


  # Create interface ports

  # Create ports
  set cam_data [ create_bd_port -dir I -from 7 -to 0 cam_data ]
  set cam_flash [ create_bd_port -dir O -from 0 -to 0 cam_flash ]
  set cam_href [ create_bd_port -dir I cam_href ]
  set cam_pclk [ create_bd_port -dir I -type clk -freq_hz 72000000 cam_pclk ]
  set cam_pwdn [ create_bd_port -dir O cam_pwdn ]
  set cam_rst_n [ create_bd_port -dir O -type rst cam_rst_n ]
  set cam_scl [ create_bd_port -dir IO cam_scl ]
  set cam_sda [ create_bd_port -dir IO cam_sda ]
  set cam_vsync [ create_bd_port -dir I cam_vsync ]
  set tmds_clk_n [ create_bd_port -dir O tmds_clk_n ]
  set tmds_clk_p [ create_bd_port -dir O tmds_clk_p ]
  set tmds_data_n [ create_bd_port -dir O -from 2 -to 0 tmds_data_n ]
  set tmds_data_p [ create_bd_port -dir O -from 2 -to 0 tmds_data_p ]

  # Create instance: axi_control, and set properties
  set axi_control [ create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect:1.0 axi_control ]
  set_property -dict [list \
    CONFIG.NUM_MI {3} \
    CONFIG.NUM_SI {1} \
  ] $axi_control


  # Create instance: axi_vdma_0, and set properties
  set axi_vdma_0 [ create_bd_cell -type ip -vlnv xilinx.com:ip:axi_vdma:6.3 axi_vdma_0 ]
  set_property -dict [list \
    CONFIG.c_include_s2mm {1} \
    CONFIG.c_m_axi_mm2s_data_width {64} \
    CONFIG.c_m_axi_s2mm_data_width {64} \
    CONFIG.c_m_axis_mm2s_tdata_width {24} \
    CONFIG.c_mm2s_linebuffer_depth {2048} \
    CONFIG.c_mm2s_max_burst_length {64} \
    CONFIG.c_num_fstores {3} \
    CONFIG.c_s2mm_genlock_mode {2} \
    CONFIG.c_s2mm_linebuffer_depth {2048} \
    CONFIG.c_s2mm_max_burst_length {64} \
  ] $axi_vdma_0


  # Create instance: axi_vdma_pose, and set properties
  set axi_vdma_pose [ create_bd_cell -type ip -vlnv xilinx.com:ip:axi_vdma:6.3 axi_vdma_pose ]
  set_property -dict [list \
    CONFIG.c_flush_on_fsync {1} \
    CONFIG.c_include_mm2s {0} \
    CONFIG.c_include_s2mm {1} \
    CONFIG.c_include_s2mm_sf {1} \
    CONFIG.c_m_axi_s2mm_data_width {64} \
    CONFIG.c_num_fstores {3} \
    CONFIG.c_s2mm_linebuffer_depth {512} \
    CONFIG.c_s2mm_max_burst_length {64} \
    CONFIG.c_s2mm_sof_enable {1} \
    CONFIG.c_use_fsync {1} \
    CONFIG.c_use_s2mm_fsync {2} \
  ] $axi_vdma_pose


  # Create instance: axi_video_memory, and set properties
  set axi_video_memory [ create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect:1.0 axi_video_memory ]
  set_property -dict [list \
    CONFIG.NUM_MI {1} \
    CONFIG.NUM_SI {3} \
  ] $axi_video_memory


  # Create instance: clk_wiz_system, and set properties
  set clk_wiz_system [ create_bd_cell -type ip -vlnv xilinx.com:ip:clk_wiz:6.0 clk_wiz_system ]
  set_property -dict [list \
    CONFIG.CLKOUT1_REQUESTED_OUT_FREQ {100.000} \
    CONFIG.CLKOUT2_REQUESTED_OUT_FREQ {200.000} \
    CONFIG.CLKOUT2_USED {true} \
    CONFIG.NUM_OUT_CLKS {2} \
    CONFIG.PRIM_SOURCE {No_buffer} \
    CONFIG.RESET_TYPE {ACTIVE_LOW} \
  ] $clk_wiz_system


  # Create instance: clk_wiz_video, and set properties
  set clk_wiz_video [ create_bd_cell -type ip -vlnv xilinx.com:ip:clk_wiz:6.0 clk_wiz_video ]
  set_property -dict [list \
    CONFIG.CLKOUT1_REQUESTED_OUT_FREQ {75.000} \
    CONFIG.CLKOUT2_REQUESTED_OUT_FREQ {187.500} \
    CONFIG.CLKOUT2_USED {true} \
    CONFIG.CLKOUT3_REQUESTED_OUT_FREQ {375.000} \
    CONFIG.CLKOUT3_USED {true} \
    CONFIG.NUM_OUT_CLKS {3} \
    CONFIG.PRIM_SOURCE {No_buffer} \
    CONFIG.RESET_TYPE {ACTIVE_HIGH} \
  ] $clk_wiz_video


  # Create instance: const_zero, and set properties
  set const_zero [ create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 const_zero ]
  set_property -dict [list \
    CONFIG.CONST_VAL {0} \
    CONFIG.CONST_WIDTH {1} \
  ] $const_zero


  # Create instance: dpu_0, and set properties
  set dpu_0 [ create_bd_cell -type ip -vlnv xilinx.com:ip:dpuczdx8g:4.1 dpu_0 ]
  set_property -dict [list \
    CONFIG.ARCH {4096} \
    CONFIG.ARCH_HP_BW {3} \
    CONFIG.ARCH_IMG_BKGRP {2} \
    CONFIG.AXI_PROTOCOL {1} \
    CONFIG.CONV_DSP_ACCU_ENA {0} \
    CONFIG.SFM_ENA {0} \
    CONFIG.S_AXI_CLK_INDEPENDENT {1} \
    CONFIG.TIME_DAY {13} \
    CONFIG.TIME_HOUR {21} \
    CONFIG.TIME_MONTH {9} \
    CONFIG.TIME_QUARTER {1} \
    CONFIG.TIME_YEAR {26} \
    CONFIG.URAM_N_USER {40} \
  ] $dpu_0


  # Create instance: dpu_irq_concat, and set properties
  set dpu_irq_concat [ create_bd_cell -type ip -vlnv xilinx.com:ip:xlconcat:2.1 dpu_irq_concat ]
  set_property CONFIG.NUM_PORTS {1} $dpu_irq_concat


  # Create instance: dvi_tx, and set properties
  set dvi_tx [ create_bd_cell -type ip -vlnv openedv.com:user:DVI_Transmitter:1.0 dvi_tx ]

  # Create instance: emio_sccb_bridge, and set properties
  set block_name emio_sccb_bridge
  set block_cell_name emio_sccb_bridge
  if { [catch {set emio_sccb_bridge [create_bd_cell -type module -reference $block_name $block_cell_name] } errmsg] } {
     catch {common::send_gid_msg -ssname BD::TCL -id 2095 -severity "ERROR" "Unable to add referenced block <$block_name>. Please add the files for ${block_name}'s definition into the project."}
     return 1
   } elseif { $emio_sccb_bridge eq "" } {
     catch {common::send_gid_msg -ssname BD::TCL -id 2096 -severity "ERROR" "Unable to referenced block <$block_name>. Please add the files for ${block_name}'s definition into the project."}
     return 1
   }
  
  # Create instance: ov5640_capture, and set properties
  set block_name ov5640_capture_data
  set block_cell_name ov5640_capture
  if { [catch {set ov5640_capture [create_bd_cell -type module -reference $block_name $block_cell_name] } errmsg] } {
     catch {common::send_gid_msg -ssname BD::TCL -id 2095 -severity "ERROR" "Unable to add referenced block <$block_name>. Please add the files for ${block_name}'s definition into the project."}
     return 1
   } elseif { $ov5640_capture eq "" } {
     catch {common::send_gid_msg -ssname BD::TCL -id 2096 -severity "ERROR" "Unable to referenced block <$block_name>. Please add the files for ${block_name}'s definition into the project."}
     return 1
   }
  
  # Create instance: pose_preprocess, and set properties
  set block_name pose_preprocess_axis
  set block_cell_name pose_preprocess
  if { [catch {set pose_preprocess [create_bd_cell -type module -reference $block_name $block_cell_name] } errmsg] } {
     catch {common::send_gid_msg -ssname BD::TCL -id 2095 -severity "ERROR" "Unable to add referenced block <$block_name>. Please add the files for ${block_name}'s definition into the project."}
     return 1
   } elseif { $pose_preprocess eq "" } {
     catch {common::send_gid_msg -ssname BD::TCL -id 2096 -severity "ERROR" "Unable to referenced block <$block_name>. Please add the files for ${block_name}'s definition into the project."}
     return 1
   }
  
  # Create instance: rst_ps_100M, and set properties
  set rst_ps_100M [ create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 rst_ps_100M ]

  # Create instance: v_tc_0, and set properties
  set v_tc_0 [ create_bd_cell -type ip -vlnv xilinx.com:ip:v_tc:6.2 v_tc_0 ]
  set_property CONFIG.enable_detection {false} $v_tc_0


  # Create instance: video_broadcast, and set properties
  set video_broadcast [ create_bd_cell -type ip -vlnv xilinx.com:ip:axis_broadcaster:1.1 video_broadcast ]
  set_property -dict [list \
    CONFIG.HAS_TLAST {1} \
    CONFIG.HAS_TREADY {1} \
    CONFIG.M_TDATA_NUM_BYTES {3} \
    CONFIG.M_TUSER_WIDTH {1} \
    CONFIG.NUM_MI {2} \
    CONFIG.S_TDATA_NUM_BYTES {3} \
    CONFIG.S_TUSER_WIDTH {1} \
  ] $video_broadcast


  # Create instance: video_in, and set properties
  set video_in [ create_bd_cell -type ip -vlnv xilinx.com:ip:v_vid_in_axi4s:5.0 video_in ]
  set_property CONFIG.C_HAS_ASYNC_CLK {1} $video_in


  # Create instance: video_out, and set properties
  set video_out [ create_bd_cell -type ip -vlnv xilinx.com:ip:v_axi4s_vid_out:4.0 video_out ]
  set_property CONFIG.C_HAS_ASYNC_CLK {1} $video_out


  # Create instance: zynq_ultra_ps_e_0, and set properties
  set zynq_ultra_ps_e_0 [ create_bd_cell -type ip -vlnv xilinx.com:ip:zynq_ultra_ps_e:3.4 zynq_ultra_ps_e_0 ]
  set_property -dict [list \
    CONFIG.PSU_BANK_0_IO_STANDARD {LVCMOS18} \
    CONFIG.PSU_BANK_1_IO_STANDARD {LVCMOS33} \
    CONFIG.PSU_BANK_2_IO_STANDARD {LVCMOS18} \
    CONFIG.PSU_BANK_3_IO_STANDARD {LVCMOS33} \
    CONFIG.PSU_DDR_RAM_HIGHADDR {0x7FFFFFFF} \
    CONFIG.PSU_DDR_RAM_HIGHADDR_OFFSET {0x00000002} \
    CONFIG.PSU_DDR_RAM_LOWADDR_OFFSET {0x80000000} \
    CONFIG.PSU_MIO_TREE_PERIPHERALS {##########################################UART 0#UART 0##################################} \
    CONFIG.PSU_MIO_TREE_SIGNALS {##########################################rxd#txd##################################} \
    CONFIG.PSU__ACT_DDR_FREQ_MHZ {799.992004} \
    CONFIG.PSU__CRF_APB__ACPU_CTRL__ACT_FREQMHZ {1333.320068} \
    CONFIG.PSU__CRF_APB__DBG_FPD_CTRL__ACT_FREQMHZ {249.997498} \
    CONFIG.PSU__CRF_APB__DBG_TSTMP_CTRL__ACT_FREQMHZ {249.997498} \
    CONFIG.PSU__CRF_APB__DDR_CTRL__ACT_FREQMHZ {399.996002} \
    CONFIG.PSU__CRF_APB__DDR_CTRL__FREQMHZ {1066} \
    CONFIG.PSU__CRF_APB__DDR_CTRL__SRCSEL {DPLL} \
    CONFIG.PSU__CRF_APB__DPDMA_REF_CTRL__ACT_FREQMHZ {599.994019} \
    CONFIG.PSU__CRF_APB__GDMA_REF_CTRL__ACT_FREQMHZ {599.994019} \
    CONFIG.PSU__CRF_APB__GPU_REF_CTRL__ACT_FREQMHZ {599.994019} \
    CONFIG.PSU__CRF_APB__TOPSW_LSBUS_CTRL__ACT_FREQMHZ {99.999001} \
    CONFIG.PSU__CRF_APB__TOPSW_MAIN_CTRL__ACT_FREQMHZ {533.328003} \
    CONFIG.PSU__CRL_APB__ADMA_REF_CTRL__ACT_FREQMHZ {533.328003} \
    CONFIG.PSU__CRL_APB__AMS_REF_CTRL__ACT_FREQMHZ {49.999500} \
    CONFIG.PSU__CRL_APB__CPU_R5_CTRL__ACT_FREQMHZ {533.328003} \
    CONFIG.PSU__CRL_APB__DBG_LPD_CTRL__ACT_FREQMHZ {249.997498} \
    CONFIG.PSU__CRL_APB__DLL_REF_CTRL__ACT_FREQMHZ {999.989990} \
    CONFIG.PSU__CRL_APB__IOU_SWITCH_CTRL__ACT_FREQMHZ {266.664001} \
    CONFIG.PSU__CRL_APB__LPD_LSBUS_CTRL__ACT_FREQMHZ {99.999001} \
    CONFIG.PSU__CRL_APB__LPD_SWITCH_CTRL__ACT_FREQMHZ {533.328003} \
    CONFIG.PSU__CRL_APB__PCAP_CTRL__ACT_FREQMHZ {199.998001} \
    CONFIG.PSU__CRL_APB__PL0_REF_CTRL__ACT_FREQMHZ {96.968727} \
    CONFIG.PSU__CRL_APB__PL0_REF_CTRL__FREQMHZ {100} \
    CONFIG.PSU__CRL_APB__TIMESTAMP_REF_CTRL__ACT_FREQMHZ {33.333000} \
    CONFIG.PSU__CRL_APB__UART0_REF_CTRL__ACT_FREQMHZ {99.999001} \
    CONFIG.PSU__DDRC__BG_ADDR_COUNT {1} \
    CONFIG.PSU__DDRC__BRC_MAPPING {ROW_BANK_COL} \
    CONFIG.PSU__DDRC__BUS_WIDTH {64 Bit} \
    CONFIG.PSU__DDRC__CL {16} \
    CONFIG.PSU__DDRC__CLOCK_STOP_EN {0} \
    CONFIG.PSU__DDRC__COMPONENTS {Components} \
    CONFIG.PSU__DDRC__CWL {11} \
    CONFIG.PSU__DDRC__DDR4_ADDR_MAPPING {1} \
    CONFIG.PSU__DDRC__DDR4_CAL_MODE_ENABLE {0} \
    CONFIG.PSU__DDRC__DDR4_CRC_CONTROL {0} \
    CONFIG.PSU__DDRC__DDR4_T_REF_MODE {0} \
    CONFIG.PSU__DDRC__DDR4_T_REF_RANGE {Normal (0-85)} \
    CONFIG.PSU__DDRC__DEVICE_CAPACITY {4096 MBits} \
    CONFIG.PSU__DDRC__DM_DBI {DM_NO_DBI} \
    CONFIG.PSU__DDRC__DRAM_WIDTH {16 Bits} \
    CONFIG.PSU__DDRC__ECC {Disabled} \
    CONFIG.PSU__DDRC__ENABLE {1} \
    CONFIG.PSU__DDRC__FGRM {1X} \
    CONFIG.PSU__DDRC__LP_ASR {manual normal} \
    CONFIG.PSU__DDRC__MEMORY_TYPE {DDR 4} \
    CONFIG.PSU__DDRC__PARITY_ENABLE {0} \
    CONFIG.PSU__DDRC__PER_BANK_REFRESH {0} \
    CONFIG.PSU__DDRC__PHY_DBI_MODE {0} \
    CONFIG.PSU__DDRC__RANK_ADDR_COUNT {0} \
    CONFIG.PSU__DDRC__ROW_ADDR_COUNT {15} \
    CONFIG.PSU__DDRC__SELF_REF_ABORT {0} \
    CONFIG.PSU__DDRC__SPEED_BIN {DDR4_2400P} \
    CONFIG.PSU__DDRC__STATIC_RD_MODE {0} \
    CONFIG.PSU__DDRC__TRAIN_DATA_EYE {1} \
    CONFIG.PSU__DDRC__TRAIN_READ_GATE {1} \
    CONFIG.PSU__DDRC__TRAIN_WRITE_LEVEL {1} \
    CONFIG.PSU__DDRC__T_FAW {30.0} \
    CONFIG.PSU__DDRC__T_RAS_MIN {32.0} \
    CONFIG.PSU__DDRC__T_RC {46.16} \
    CONFIG.PSU__DDRC__T_RCD {16} \
    CONFIG.PSU__DDRC__T_RP {16} \
    CONFIG.PSU__DDRC__VREF {1} \
    CONFIG.PSU__DDR_HIGH_ADDRESS_GUI_ENABLE {0} \
    CONFIG.PSU__DDR__INTERFACE__FREQMHZ {533.000} \
    CONFIG.PSU__FPGA_PL0_ENABLE {1} \
    CONFIG.PSU__GPIO_EMIO_WIDTH {95} \
    CONFIG.PSU__GPIO_EMIO__PERIPHERAL__ENABLE {1} \
    CONFIG.PSU__GPIO_EMIO__PERIPHERAL__IO {95} \
    CONFIG.PSU__MAXIGP0__DATA_WIDTH {32} \
    CONFIG.PSU__MAXIGP1__DATA_WIDTH {32} \
    CONFIG.PSU__PL_CLK0_BUF {TRUE} \
    CONFIG.PSU__PROTECTION__MASTERS {USB1:NonSecure;0|USB0:NonSecure;0|S_AXI_LPD:NA;0|S_AXI_HPC1_FPD:NA;0|S_AXI_HPC0_FPD:NA;0|S_AXI_HP3_FPD:NA;1|S_AXI_HP2_FPD:NA;1|S_AXI_HP1_FPD:NA;1|S_AXI_HP0_FPD:NA;1|S_AXI_ACP:NA;0|S_AXI_ACE:NA;0|SD1:NonSecure;0|SD0:NonSecure;0|SATA1:NonSecure;0|SATA0:NonSecure;0|RPU1:Secure;1|RPU0:Secure;1|QSPI:NonSecure;0|PMU:NA;1|PCIe:NonSecure;0|NAND:NonSecure;0|LDMA:NonSecure;1|GPU:NonSecure;1|GEM3:NonSecure;0|GEM2:NonSecure;0|GEM1:NonSecure;0|GEM0:NonSecure;0|FDMA:NonSecure;1|DP:NonSecure;0|DAP:NA;1|Coresight:NA;1|CSU:NA;1|APU:NA;1}\
\
    CONFIG.PSU__PROTECTION__SLAVES {LPD;USB3_1_XHCI;FE300000;FE3FFFFF;0|LPD;USB3_1;FF9E0000;FF9EFFFF;0|LPD;USB3_0_XHCI;FE200000;FE2FFFFF;0|LPD;USB3_0;FF9D0000;FF9DFFFF;0|LPD;UART1;FF010000;FF01FFFF;0|LPD;UART0;FF000000;FF00FFFF;1|LPD;TTC3;FF140000;FF14FFFF;0|LPD;TTC2;FF130000;FF13FFFF;0|LPD;TTC1;FF120000;FF12FFFF;0|LPD;TTC0;FF110000;FF11FFFF;0|FPD;SWDT1;FD4D0000;FD4DFFFF;0|LPD;SWDT0;FF150000;FF15FFFF;0|LPD;SPI1;FF050000;FF05FFFF;0|LPD;SPI0;FF040000;FF04FFFF;0|FPD;SMMU_REG;FD5F0000;FD5FFFFF;1|FPD;SMMU;FD800000;FDFFFFFF;1|FPD;SIOU;FD3D0000;FD3DFFFF;1|FPD;SERDES;FD400000;FD47FFFF;1|LPD;SD1;FF170000;FF17FFFF;0|LPD;SD0;FF160000;FF16FFFF;0|FPD;SATA;FD0C0000;FD0CFFFF;0|LPD;RTC;FFA60000;FFA6FFFF;1|LPD;RSA_CORE;FFCE0000;FFCEFFFF;1|LPD;RPU;FF9A0000;FF9AFFFF;1|LPD;R5_TCM_RAM_GLOBAL;FFE00000;FFE3FFFF;1|LPD;R5_1_Instruction_Cache;FFEC0000;FFECFFFF;1|LPD;R5_1_Data_Cache;FFED0000;FFEDFFFF;1|LPD;R5_1_BTCM_GLOBAL;FFEB0000;FFEBFFFF;1|LPD;R5_1_ATCM_GLOBAL;FFE90000;FFE9FFFF;1|LPD;R5_0_Instruction_Cache;FFE40000;FFE4FFFF;1|LPD;R5_0_Data_Cache;FFE50000;FFE5FFFF;1|LPD;R5_0_BTCM_GLOBAL;FFE20000;FFE2FFFF;1|LPD;R5_0_ATCM_GLOBAL;FFE00000;FFE0FFFF;1|LPD;QSPI_Linear_Address;C0000000;DFFFFFFF;1|LPD;QSPI;FF0F0000;FF0FFFFF;0|LPD;PMU_RAM;FFDC0000;FFDDFFFF;1|LPD;PMU_GLOBAL;FFD80000;FFDBFFFF;1|FPD;PCIE_MAIN;FD0E0000;FD0EFFFF;0|FPD;PCIE_LOW;E0000000;EFFFFFFF;0|FPD;PCIE_HIGH2;8000000000;BFFFFFFFFF;0|FPD;PCIE_HIGH1;600000000;7FFFFFFFF;0|FPD;PCIE_DMA;FD0F0000;FD0FFFFF;0|FPD;PCIE_ATTRIB;FD480000;FD48FFFF;0|LPD;OCM_XMPU_CFG;FFA70000;FFA7FFFF;1|LPD;OCM_SLCR;FF960000;FF96FFFF;1|OCM;OCM;FFFC0000;FFFFFFFF;1|LPD;NAND;FF100000;FF10FFFF;0|LPD;MBISTJTAG;FFCF0000;FFCFFFFF;1|LPD;LPD_XPPU_SINK;FF9C0000;FF9CFFFF;1|LPD;LPD_XPPU;FF980000;FF98FFFF;1|LPD;LPD_SLCR_SECURE;FF4B0000;FF4DFFFF;1|LPD;LPD_SLCR;FF410000;FF4AFFFF;1|LPD;LPD_GPV;FE100000;FE1FFFFF;1|LPD;LPD_DMA_7;FFAF0000;FFAFFFFF;1|LPD;LPD_DMA_6;FFAE0000;FFAEFFFF;1|LPD;LPD_DMA_5;FFAD0000;FFADFFFF;1|LPD;LPD_DMA_4;FFAC0000;FFACFFFF;1|LPD;LPD_DMA_3;FFAB0000;FFABFFFF;1|LPD;LPD_DMA_2;FFAA0000;FFAAFFFF;1|LPD;LPD_DMA_1;FFA90000;FFA9FFFF;1|LPD;LPD_DMA_0;FFA80000;FFA8FFFF;1|LPD;IPI_CTRL;FF380000;FF3FFFFF;1|LPD;IOU_SLCR;FF180000;FF23FFFF;1|LPD;IOU_SECURE_SLCR;FF240000;FF24FFFF;1|LPD;IOU_SCNTRS;FF260000;FF26FFFF;1|LPD;IOU_SCNTR;FF250000;FF25FFFF;1|LPD;IOU_GPV;FE000000;FE0FFFFF;1|LPD;I2C1;FF030000;FF03FFFF;0|LPD;I2C0;FF020000;FF02FFFF;0|FPD;GPU;FD4B0000;FD4BFFFF;1|LPD;GPIO;FF0A0000;FF0AFFFF;1|LPD;GEM3;FF0E0000;FF0EFFFF;0|LPD;GEM2;FF0D0000;FF0DFFFF;0|LPD;GEM1;FF0C0000;FF0CFFFF;0|LPD;GEM0;FF0B0000;FF0BFFFF;0|FPD;FPD_XMPU_SINK;FD4F0000;FD4FFFFF;1|FPD;FPD_XMPU_CFG;FD5D0000;FD5DFFFF;1|FPD;FPD_SLCR_SECURE;FD690000;FD6CFFFF;1|FPD;FPD_SLCR;FD610000;FD68FFFF;1|FPD;FPD_DMA_CH7;FD570000;FD57FFFF;1|FPD;FPD_DMA_CH6;FD560000;FD56FFFF;1|FPD;FPD_DMA_CH5;FD550000;FD55FFFF;1|FPD;FPD_DMA_CH4;FD540000;FD54FFFF;1|FPD;FPD_DMA_CH3;FD530000;FD53FFFF;1|FPD;FPD_DMA_CH2;FD520000;FD52FFFF;1|FPD;FPD_DMA_CH1;FD510000;FD51FFFF;1|FPD;FPD_DMA_CH0;FD500000;FD50FFFF;1|LPD;EFUSE;FFCC0000;FFCCFFFF;1|FPD;Display\
Port;FD4A0000;FD4AFFFF;0|FPD;DPDMA;FD4C0000;FD4CFFFF;0|FPD;DDR_XMPU5_CFG;FD050000;FD05FFFF;1|FPD;DDR_XMPU4_CFG;FD040000;FD04FFFF;1|FPD;DDR_XMPU3_CFG;FD030000;FD03FFFF;1|FPD;DDR_XMPU2_CFG;FD020000;FD02FFFF;1|FPD;DDR_XMPU1_CFG;FD010000;FD01FFFF;1|FPD;DDR_XMPU0_CFG;FD000000;FD00FFFF;1|FPD;DDR_QOS_CTRL;FD090000;FD09FFFF;1|FPD;DDR_PHY;FD080000;FD08FFFF;1|DDR;DDR_LOW;0;7FFFFFFF;1|DDR;DDR_HIGH;800000000;800000000;0|FPD;DDDR_CTRL;FD070000;FD070FFF;1|LPD;Coresight;FE800000;FEFFFFFF;1|LPD;CSU_DMA;FFC80000;FFC9FFFF;1|LPD;CSU;FFCA0000;FFCAFFFF;1|LPD;CRL_APB;FF5E0000;FF85FFFF;1|FPD;CRF_APB;FD1A0000;FD2DFFFF;1|FPD;CCI_REG;FD5E0000;FD5EFFFF;1|LPD;CAN1;FF070000;FF07FFFF;0|LPD;CAN0;FF060000;FF06FFFF;0|FPD;APU;FD5C0000;FD5CFFFF;1|LPD;APM_INTC_IOU;FFA20000;FFA2FFFF;1|LPD;APM_FPD_LPD;FFA30000;FFA3FFFF;1|FPD;APM_5;FD490000;FD49FFFF;1|FPD;APM_0;FD0B0000;FD0BFFFF;1|LPD;APM2;FFA10000;FFA1FFFF;1|LPD;APM1;FFA00000;FFA0FFFF;1|LPD;AMS;FFA50000;FFA5FFFF;1|FPD;AFI_5;FD3B0000;FD3BFFFF;1|FPD;AFI_4;FD3A0000;FD3AFFFF;1|FPD;AFI_3;FD390000;FD39FFFF;1|FPD;AFI_2;FD380000;FD38FFFF;1|FPD;AFI_1;FD370000;FD37FFFF;1|FPD;AFI_0;FD360000;FD36FFFF;1|LPD;AFIFM6;FF9B0000;FF9BFFFF;1|FPD;ACPU_GIC;F9010000;F907FFFF;1}\
\
    CONFIG.PSU__SAXIGP2__DATA_WIDTH {32} \
    CONFIG.PSU__SAXIGP3__DATA_WIDTH {128} \
    CONFIG.PSU__SAXIGP4__DATA_WIDTH {128} \
    CONFIG.PSU__SAXIGP5__DATA_WIDTH {128} \
    CONFIG.PSU__UART0__BAUD_RATE {115200} \
    CONFIG.PSU__UART0__MODEM__ENABLE {0} \
    CONFIG.PSU__UART0__PERIPHERAL__ENABLE {1} \
    CONFIG.PSU__UART0__PERIPHERAL__IO {MIO 42 .. 43} \
    CONFIG.PSU__USE__DDR_INTF_REQUESTED {1} \
    CONFIG.PSU__USE__IRQ0 {1} \
    CONFIG.PSU__USE__M_AXI_GP0 {1} \
    CONFIG.PSU__USE__M_AXI_GP1 {1} \
    CONFIG.PSU__USE__M_AXI_GP2 {0} \
    CONFIG.PSU__USE__S_AXI_GP2 {1} \
    CONFIG.PSU__USE__S_AXI_GP3 {1} \
    CONFIG.PSU__USE__S_AXI_GP4 {1} \
    CONFIG.PSU__USE__S_AXI_GP5 {1} \
  ] $zynq_ultra_ps_e_0


  # Create interface connections
  connect_bd_intf_net -intf_net axi_control_M00_AXI [get_bd_intf_pins axi_control/M00_AXI] [get_bd_intf_pins axi_vdma_0/S_AXI_LITE]
  connect_bd_intf_net -intf_net axi_control_M01_AXI [get_bd_intf_pins axi_control/M01_AXI] [get_bd_intf_pins axi_vdma_pose/S_AXI_LITE]
  connect_bd_intf_net -intf_net axi_control_M02_AXI [get_bd_intf_pins axi_control/M02_AXI] [get_bd_intf_pins v_tc_0/ctrl]
  connect_bd_intf_net -intf_net axi_vdma_0_M_AXIS_MM2S [get_bd_intf_pins axi_vdma_0/M_AXIS_MM2S] [get_bd_intf_pins video_out/video_in]
  connect_bd_intf_net -intf_net axi_vdma_0_M_AXI_MM2S [get_bd_intf_pins axi_vdma_0/M_AXI_MM2S] [get_bd_intf_pins axi_video_memory/S00_AXI]
  connect_bd_intf_net -intf_net axi_vdma_0_M_AXI_S2MM [get_bd_intf_pins axi_vdma_0/M_AXI_S2MM] [get_bd_intf_pins axi_video_memory/S01_AXI]
  connect_bd_intf_net -intf_net axi_vdma_pose_M_AXI_S2MM [get_bd_intf_pins axi_vdma_pose/M_AXI_S2MM] [get_bd_intf_pins axi_video_memory/S02_AXI]
  connect_bd_intf_net -intf_net axi_video_memory_M00_AXI [get_bd_intf_pins axi_video_memory/M00_AXI] [get_bd_intf_pins zynq_ultra_ps_e_0/S_AXI_HP3_FPD]
  connect_bd_intf_net -intf_net dpu_0_DPU0_M_AXI_DATA0 [get_bd_intf_pins dpu_0/DPU0_M_AXI_DATA0] [get_bd_intf_pins zynq_ultra_ps_e_0/S_AXI_HP1_FPD]
  connect_bd_intf_net -intf_net dpu_0_DPU0_M_AXI_DATA1 [get_bd_intf_pins dpu_0/DPU0_M_AXI_DATA1] [get_bd_intf_pins zynq_ultra_ps_e_0/S_AXI_HP2_FPD]
  connect_bd_intf_net -intf_net dpu_0_DPU0_M_AXI_INSTR [get_bd_intf_pins dpu_0/DPU0_M_AXI_INSTR] [get_bd_intf_pins zynq_ultra_ps_e_0/S_AXI_HP0_FPD]
  connect_bd_intf_net -intf_net pose_preprocess_m_axis [get_bd_intf_pins axi_vdma_pose/S_AXIS_S2MM] [get_bd_intf_pins pose_preprocess/m_axis]
  connect_bd_intf_net -intf_net v_tc_0_vtiming_out [get_bd_intf_pins v_tc_0/vtiming_out] [get_bd_intf_pins video_out/vtiming_in]
  connect_bd_intf_net -intf_net video_broadcast_M00_AXIS [get_bd_intf_pins axi_vdma_0/S_AXIS_S2MM] [get_bd_intf_pins video_broadcast/M00_AXIS]
  connect_bd_intf_net -intf_net video_broadcast_M01_AXIS [get_bd_intf_pins pose_preprocess/s_axis] [get_bd_intf_pins video_broadcast/M01_AXIS]
  connect_bd_intf_net -intf_net video_in_video_out [get_bd_intf_pins video_broadcast/S_AXIS] [get_bd_intf_pins video_in/video_out]
  connect_bd_intf_net -intf_net video_out_vid_io_out [get_bd_intf_pins dvi_tx/Video_In] [get_bd_intf_pins video_out/vid_io_out]
  connect_bd_intf_net -intf_net zynq_ultra_ps_e_0_M_AXI_HPM0_FPD [get_bd_intf_pins axi_control/S00_AXI] [get_bd_intf_pins zynq_ultra_ps_e_0/M_AXI_HPM0_FPD]
  connect_bd_intf_net -intf_net zynq_ultra_ps_e_0_M_AXI_HPM1_FPD [get_bd_intf_pins dpu_0/S_AXI] [get_bd_intf_pins zynq_ultra_ps_e_0/M_AXI_HPM1_FPD]

  # Create port connections
  connect_bd_net -net Net [get_bd_ports cam_scl] [get_bd_pins emio_sccb_bridge/sccb_scl]
  connect_bd_net -net Net1 [get_bd_ports cam_sda] [get_bd_pins emio_sccb_bridge/sccb_sda]
  connect_bd_net -net cam_data_1 [get_bd_ports cam_data] [get_bd_pins ov5640_capture/cam_data]
  connect_bd_net -net cam_href_1 [get_bd_ports cam_href] [get_bd_pins ov5640_capture/cam_href]
  connect_bd_net -net cam_pclk_1 [get_bd_ports cam_pclk] [get_bd_pins ov5640_capture/cam_pclk]
  connect_bd_net -net cam_vsync_1 [get_bd_ports cam_vsync] [get_bd_pins ov5640_capture/cam_vsync]
  connect_bd_net -net clk_wiz_system_clk_out1 [get_bd_pins axi_control/aclk] [get_bd_pins axi_vdma_0/m_axi_mm2s_aclk] [get_bd_pins axi_vdma_0/m_axi_s2mm_aclk] [get_bd_pins axi_vdma_0/m_axis_mm2s_aclk] [get_bd_pins axi_vdma_0/s_axi_lite_aclk] [get_bd_pins axi_vdma_0/s_axis_s2mm_aclk] [get_bd_pins axi_vdma_pose/m_axi_s2mm_aclk] [get_bd_pins axi_vdma_pose/s_axi_lite_aclk] [get_bd_pins axi_vdma_pose/s_axis_s2mm_aclk] [get_bd_pins axi_video_memory/aclk] [get_bd_pins clk_wiz_system/clk_out1] [get_bd_pins clk_wiz_video/clk_in1] [get_bd_pins dpu_0/m_axi_dpu_aclk] [get_bd_pins dpu_0/s_axi_aclk] [get_bd_pins pose_preprocess/aclk] [get_bd_pins rst_ps_100M/slowest_sync_clk] [get_bd_pins v_tc_0/s_axi_aclk] [get_bd_pins video_broadcast/aclk] [get_bd_pins video_in/aclk] [get_bd_pins video_out/aclk] [get_bd_pins zynq_ultra_ps_e_0/maxihpm0_fpd_aclk] [get_bd_pins zynq_ultra_ps_e_0/maxihpm1_fpd_aclk] [get_bd_pins zynq_ultra_ps_e_0/saxihp0_fpd_aclk] [get_bd_pins zynq_ultra_ps_e_0/saxihp1_fpd_aclk] [get_bd_pins zynq_ultra_ps_e_0/saxihp2_fpd_aclk] [get_bd_pins zynq_ultra_ps_e_0/saxihp3_fpd_aclk]
  connect_bd_net -net clk_wiz_system_clk_out2 [get_bd_pins clk_wiz_system/clk_out2] [get_bd_pins dpu_0/dpu_2x_clk]
  connect_bd_net -net clk_wiz_system_locked [get_bd_pins clk_wiz_system/locked] [get_bd_pins rst_ps_100M/dcm_locked]
  connect_bd_net -net clk_wiz_video_clk_out1 [get_bd_pins clk_wiz_video/clk_out1] [get_bd_pins dvi_tx/pclk] [get_bd_pins v_tc_0/clk] [get_bd_pins video_out/vid_io_out_clk]
  connect_bd_net -net clk_wiz_video_clk_out2 [get_bd_pins clk_wiz_video/clk_out2] [get_bd_pins dvi_tx/pixel_clk_2_5x]
  connect_bd_net -net clk_wiz_video_clk_out3 [get_bd_pins clk_wiz_video/clk_out3] [get_bd_pins dvi_tx/pixel_clk_5x]
  connect_bd_net -net clk_wiz_video_locked [get_bd_pins clk_wiz_video/locked] [get_bd_pins dvi_tx/reset_n] [get_bd_pins ov5640_capture/rst_n]
  connect_bd_net -net const_zero_dout [get_bd_ports cam_flash] [get_bd_pins const_zero/dout] [get_bd_pins video_in/vid_hsync]
  connect_bd_net -net dpu_0_dpu0_interrupt [get_bd_pins dpu_0/dpu0_interrupt] [get_bd_pins dpu_irq_concat/In0]
  connect_bd_net -net dpu_irq_concat_dout [get_bd_pins dpu_irq_concat/dout] [get_bd_pins zynq_ultra_ps_e_0/pl_ps_irq0]
  connect_bd_net -net dvi_tx_tmds_clk_n [get_bd_ports tmds_clk_n] [get_bd_pins dvi_tx/tmds_clk_n]
  connect_bd_net -net dvi_tx_tmds_clk_p [get_bd_ports tmds_clk_p] [get_bd_pins dvi_tx/tmds_clk_p]
  connect_bd_net -net dvi_tx_tmds_data_n [get_bd_ports tmds_data_n] [get_bd_pins dvi_tx/tmds_data_n]
  connect_bd_net -net dvi_tx_tmds_data_p [get_bd_ports tmds_data_p] [get_bd_pins dvi_tx/tmds_data_p]
  connect_bd_net -net emio_sccb_bridge_gpio_i [get_bd_pins emio_sccb_bridge/gpio_i] [get_bd_pins zynq_ultra_ps_e_0/emio_gpio_i]
  connect_bd_net -net ov5640_capture_cam_pwdn [get_bd_ports cam_pwdn] [get_bd_pins ov5640_capture/cam_pwdn]
  connect_bd_net -net ov5640_capture_cam_rst_n [get_bd_ports cam_rst_n] [get_bd_pins ov5640_capture/cam_rst_n]
  connect_bd_net -net ov5640_capture_vid_active_video [get_bd_pins ov5640_capture/vid_active_video] [get_bd_pins video_in/vid_active_video]
  connect_bd_net -net ov5640_capture_vid_ce [get_bd_pins ov5640_capture/vid_ce] [get_bd_pins video_in/vid_io_in_ce]
  connect_bd_net -net ov5640_capture_vid_clk [get_bd_pins ov5640_capture/vid_clk] [get_bd_pins video_in/vid_io_in_clk]
  connect_bd_net -net ov5640_capture_vid_data [get_bd_pins ov5640_capture/vid_data] [get_bd_pins video_in/vid_data]
  connect_bd_net -net ov5640_capture_vid_vsync [get_bd_pins ov5640_capture/vid_vsync] [get_bd_pins video_in/vid_vsync]
  connect_bd_net -net rst_ps_100M_peripheral_aresetn [get_bd_pins axi_control/aresetn] [get_bd_pins axi_vdma_0/axi_resetn] [get_bd_pins axi_vdma_pose/axi_resetn] [get_bd_pins axi_video_memory/aresetn] [get_bd_pins dpu_0/dpu_2x_resetn] [get_bd_pins dpu_0/m_axi_dpu_aresetn] [get_bd_pins dpu_0/s_axi_aresetn] [get_bd_pins pose_preprocess/aresetn] [get_bd_pins rst_ps_100M/peripheral_aresetn] [get_bd_pins v_tc_0/s_axi_aresetn] [get_bd_pins video_broadcast/aresetn]
  connect_bd_net -net rst_ps_100M_peripheral_reset [get_bd_pins clk_wiz_video/reset] [get_bd_pins rst_ps_100M/peripheral_reset]
  connect_bd_net -net video_out_vtg_ce [get_bd_pins v_tc_0/gen_clken] [get_bd_pins video_out/vtg_ce]
  connect_bd_net -net zynq_ultra_ps_e_0_emio_gpio_o [get_bd_pins emio_sccb_bridge/gpio_o] [get_bd_pins zynq_ultra_ps_e_0/emio_gpio_o]
  connect_bd_net -net zynq_ultra_ps_e_0_emio_gpio_t [get_bd_pins emio_sccb_bridge/gpio_t] [get_bd_pins zynq_ultra_ps_e_0/emio_gpio_t]
  connect_bd_net -net zynq_ultra_ps_e_0_pl_clk0 [get_bd_pins clk_wiz_system/clk_in1] [get_bd_pins zynq_ultra_ps_e_0/pl_clk0]
  connect_bd_net -net zynq_ultra_ps_e_0_pl_resetn0 [get_bd_pins clk_wiz_system/resetn] [get_bd_pins rst_ps_100M/ext_reset_in] [get_bd_pins zynq_ultra_ps_e_0/pl_resetn0]

  # Create address segments
  assign_bd_address -offset 0x00000000 -range 0x80000000 -target_address_space [get_bd_addr_spaces axi_vdma_0/Data_MM2S] [get_bd_addr_segs zynq_ultra_ps_e_0/SAXIGP5/HP3_DDR_LOW] -force
  assign_bd_address -offset 0x00000000 -range 0x80000000 -target_address_space [get_bd_addr_spaces axi_vdma_0/Data_S2MM] [get_bd_addr_segs zynq_ultra_ps_e_0/SAXIGP5/HP3_DDR_LOW] -force
  assign_bd_address -offset 0x00000000 -range 0x80000000 -target_address_space [get_bd_addr_spaces axi_vdma_pose/Data_S2MM] [get_bd_addr_segs zynq_ultra_ps_e_0/SAXIGP5/HP3_DDR_LOW] -force
  assign_bd_address -offset 0x00000000 -range 0x80000000 -target_address_space [get_bd_addr_spaces dpu_0/DPU0_M_AXI_DATA0] [get_bd_addr_segs zynq_ultra_ps_e_0/SAXIGP3/HP1_DDR_LOW] -force
  assign_bd_address -offset 0xFF000000 -range 0x01000000 -target_address_space [get_bd_addr_spaces dpu_0/DPU0_M_AXI_DATA0] [get_bd_addr_segs zynq_ultra_ps_e_0/SAXIGP3/HP1_LPS_OCM] -force
  assign_bd_address -offset 0x00000000 -range 0x80000000 -target_address_space [get_bd_addr_spaces dpu_0/DPU0_M_AXI_DATA1] [get_bd_addr_segs zynq_ultra_ps_e_0/SAXIGP4/HP2_DDR_LOW] -force
  assign_bd_address -offset 0xFF000000 -range 0x01000000 -target_address_space [get_bd_addr_spaces dpu_0/DPU0_M_AXI_DATA1] [get_bd_addr_segs zynq_ultra_ps_e_0/SAXIGP4/HP2_LPS_OCM] -force
  assign_bd_address -offset 0x00000000 -range 0x80000000 -target_address_space [get_bd_addr_spaces dpu_0/DPU0_M_AXI_INSTR] [get_bd_addr_segs zynq_ultra_ps_e_0/SAXIGP2/HP0_DDR_LOW] -force
  assign_bd_address -offset 0xFF000000 -range 0x01000000 -target_address_space [get_bd_addr_spaces dpu_0/DPU0_M_AXI_INSTR] [get_bd_addr_segs zynq_ultra_ps_e_0/SAXIGP2/HP0_LPS_OCM] -force
  assign_bd_address -offset 0xA0000000 -range 0x00010000 -target_address_space [get_bd_addr_spaces zynq_ultra_ps_e_0/Data] [get_bd_addr_segs axi_vdma_0/S_AXI_LITE/Reg] -force
  assign_bd_address -offset 0xA0010000 -range 0x00010000 -target_address_space [get_bd_addr_spaces zynq_ultra_ps_e_0/Data] [get_bd_addr_segs axi_vdma_pose/S_AXI_LITE/Reg] -force
  assign_bd_address -offset 0x000500000000 -range 0x01000000 -target_address_space [get_bd_addr_spaces zynq_ultra_ps_e_0/Data] [get_bd_addr_segs dpu_0/S_AXI/reg0] -force
  assign_bd_address -offset 0xA0020000 -range 0x00010000 -target_address_space [get_bd_addr_spaces zynq_ultra_ps_e_0/Data] [get_bd_addr_segs v_tc_0/ctrl/Reg] -force

  # Exclude Address Segments
  exclude_bd_addr_seg -offset 0xFF000000 -range 0x01000000 -target_address_space [get_bd_addr_spaces axi_vdma_0/Data_MM2S] [get_bd_addr_segs zynq_ultra_ps_e_0/SAXIGP5/HP3_LPS_OCM]
  exclude_bd_addr_seg -offset 0xFF000000 -range 0x01000000 -target_address_space [get_bd_addr_spaces axi_vdma_0/Data_S2MM] [get_bd_addr_segs zynq_ultra_ps_e_0/SAXIGP5/HP3_LPS_OCM]
  exclude_bd_addr_seg -offset 0xFF000000 -range 0x01000000 -target_address_space [get_bd_addr_spaces axi_vdma_pose/Data_S2MM] [get_bd_addr_segs zynq_ultra_ps_e_0/SAXIGP5/HP3_LPS_OCM]


  # Restore current instance
  current_bd_instance $oldCurInst

  validate_bd_design
  save_bd_design
}
# End of create_root_design()


##################################################################
# MAIN FLOW
##################################################################

create_root_design ""


