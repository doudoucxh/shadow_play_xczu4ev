// ==============================================================
// Vitis HLS - High-Level Synthesis from C, C++ and OpenCL v2022.2 (64-bit)
// Tool Version Limit: 2019.12
// Copyright 1986-2022 Xilinx, Inc. All Rights Reserved.
// ==============================================================
// control
// 0x00 : Control signals
//        bit 0  - ap_start (Read/Write/COH)
//        bit 1  - ap_done (Read/COR)
//        bit 2  - ap_idle (Read)
//        bit 3  - ap_ready (Read/COR)
//        bit 7  - auto_restart (Read/Write)
//        bit 9  - interrupt (Read)
//        others - reserved
// 0x04 : Global Interrupt Enable Register
//        bit 0  - Global Interrupt Enable (Read/Write)
//        others - reserved
// 0x08 : IP Interrupt Enable Register (Read/Write)
//        bit 0 - enable ap_done interrupt (Read/Write)
//        bit 1 - enable ap_ready interrupt (Read/Write)
//        others - reserved
// 0x0c : IP Interrupt Status Register (Read/TOW)
//        bit 0 - ap_done (Read/TOW)
//        bit 1 - ap_ready (Read/TOW)
//        others - reserved
// 0x10 : Data signal of input_raw
//        bit 31~0 - input_raw[31:0] (Read/Write)
// 0x14 : Data signal of input_raw
//        bit 31~0 - input_raw[63:32] (Read/Write)
// 0x18 : reserved
// 0x1c : Data signal of input_r
//        bit 31~0 - input_r[31:0] (Read/Write)
// 0x20 : Data signal of input_r
//        bit 31~0 - input_r[63:32] (Read/Write)
// 0x24 : reserved
// 0x28 : Data signal of input_lut
//        bit 31~0 - input_lut[31:0] (Read/Write)
// 0x2c : Data signal of input_lut
//        bit 31~0 - input_lut[63:32] (Read/Write)
// 0x30 : reserved
// 0x34 : Data signal of dw_weights
//        bit 31~0 - dw_weights[31:0] (Read/Write)
// 0x38 : Data signal of dw_weights
//        bit 31~0 - dw_weights[63:32] (Read/Write)
// 0x3c : reserved
// 0x40 : Data signal of dw_params
//        bit 31~0 - dw_params[31:0] (Read/Write)
// 0x44 : Data signal of dw_params
//        bit 31~0 - dw_params[63:32] (Read/Write)
// 0x48 : reserved
// 0x4c : Data signal of pw_weights
//        bit 31~0 - pw_weights[31:0] (Read/Write)
// 0x50 : Data signal of pw_weights
//        bit 31~0 - pw_weights[63:32] (Read/Write)
// 0x54 : reserved
// 0x58 : Data signal of pw_params
//        bit 31~0 - pw_params[31:0] (Read/Write)
// 0x5c : Data signal of pw_params
//        bit 31~0 - pw_params[63:32] (Read/Write)
// 0x60 : reserved
// 0x64 : Data signal of residual
//        bit 31~0 - residual[31:0] (Read/Write)
// 0x68 : Data signal of residual
//        bit 31~0 - residual[63:32] (Read/Write)
// 0x6c : reserved
// 0x70 : Data signal of output_r
//        bit 31~0 - output_r[31:0] (Read/Write)
// 0x74 : Data signal of output_r
//        bit 31~0 - output_r[63:32] (Read/Write)
// 0x78 : reserved
// 0x7c : Data signal of operation
//        bit 31~0 - operation[31:0] (Read/Write)
// 0x80 : reserved
// 0x84 : Data signal of height
//        bit 31~0 - height[31:0] (Read/Write)
// 0x88 : reserved
// 0x8c : Data signal of width
//        bit 31~0 - width[31:0] (Read/Write)
// 0x90 : reserved
// 0x94 : Data signal of input_channels
//        bit 31~0 - input_channels[31:0] (Read/Write)
// 0x98 : reserved
// 0x9c : Data signal of output_channels
//        bit 31~0 - output_channels[31:0] (Read/Write)
// 0xa0 : reserved
// 0xa4 : Data signal of stride
//        bit 31~0 - stride[31:0] (Read/Write)
// 0xa8 : reserved
// 0xac : Data signal of input_zero_point
//        bit 31~0 - input_zero_point[31:0] (Read/Write)
// 0xb0 : reserved
// 0xb4 : Data signal of dw_output_zero_point
//        bit 31~0 - dw_output_zero_point[31:0] (Read/Write)
// 0xb8 : reserved
// 0xbc : Data signal of output_zero_point
//        bit 31~0 - output_zero_point[31:0] (Read/Write)
// 0xc0 : reserved
// 0xc4 : Data signal of residual_zero_point
//        bit 31~0 - residual_zero_point[31:0] (Read/Write)
// 0xc8 : reserved
// 0xcc : Data signal of residual_multiplier
//        bit 31~0 - residual_multiplier[31:0] (Read/Write)
// 0xd0 : reserved
// 0xd4 : Data signal of residual_shift
//        bit 31~0 - residual_shift[31:0] (Read/Write)
// 0xd8 : reserved
// 0xdc : Data signal of relu_enable
//        bit 31~0 - relu_enable[31:0] (Read/Write)
// 0xe0 : reserved
// 0xe4 : Data signal of residual_enable
//        bit 31~0 - residual_enable[31:0] (Read/Write)
// 0xe8 : reserved
// (SC = Self Clear, COR = Clear on Read, TOW = Toggle on Write, COH = Clear on Handshake)

#define XPOSE_CNN_ACCEL_CONTROL_ADDR_AP_CTRL                   0x00
#define XPOSE_CNN_ACCEL_CONTROL_ADDR_GIE                       0x04
#define XPOSE_CNN_ACCEL_CONTROL_ADDR_IER                       0x08
#define XPOSE_CNN_ACCEL_CONTROL_ADDR_ISR                       0x0c
#define XPOSE_CNN_ACCEL_CONTROL_ADDR_INPUT_RAW_DATA            0x10
#define XPOSE_CNN_ACCEL_CONTROL_BITS_INPUT_RAW_DATA            64
#define XPOSE_CNN_ACCEL_CONTROL_ADDR_INPUT_R_DATA              0x1c
#define XPOSE_CNN_ACCEL_CONTROL_BITS_INPUT_R_DATA              64
#define XPOSE_CNN_ACCEL_CONTROL_ADDR_INPUT_LUT_DATA            0x28
#define XPOSE_CNN_ACCEL_CONTROL_BITS_INPUT_LUT_DATA            64
#define XPOSE_CNN_ACCEL_CONTROL_ADDR_DW_WEIGHTS_DATA           0x34
#define XPOSE_CNN_ACCEL_CONTROL_BITS_DW_WEIGHTS_DATA           64
#define XPOSE_CNN_ACCEL_CONTROL_ADDR_DW_PARAMS_DATA            0x40
#define XPOSE_CNN_ACCEL_CONTROL_BITS_DW_PARAMS_DATA            64
#define XPOSE_CNN_ACCEL_CONTROL_ADDR_PW_WEIGHTS_DATA           0x4c
#define XPOSE_CNN_ACCEL_CONTROL_BITS_PW_WEIGHTS_DATA           64
#define XPOSE_CNN_ACCEL_CONTROL_ADDR_PW_PARAMS_DATA            0x58
#define XPOSE_CNN_ACCEL_CONTROL_BITS_PW_PARAMS_DATA            64
#define XPOSE_CNN_ACCEL_CONTROL_ADDR_RESIDUAL_DATA             0x64
#define XPOSE_CNN_ACCEL_CONTROL_BITS_RESIDUAL_DATA             64
#define XPOSE_CNN_ACCEL_CONTROL_ADDR_OUTPUT_R_DATA             0x70
#define XPOSE_CNN_ACCEL_CONTROL_BITS_OUTPUT_R_DATA             64
#define XPOSE_CNN_ACCEL_CONTROL_ADDR_OPERATION_DATA            0x7c
#define XPOSE_CNN_ACCEL_CONTROL_BITS_OPERATION_DATA            32
#define XPOSE_CNN_ACCEL_CONTROL_ADDR_HEIGHT_DATA               0x84
#define XPOSE_CNN_ACCEL_CONTROL_BITS_HEIGHT_DATA               32
#define XPOSE_CNN_ACCEL_CONTROL_ADDR_WIDTH_DATA                0x8c
#define XPOSE_CNN_ACCEL_CONTROL_BITS_WIDTH_DATA                32
#define XPOSE_CNN_ACCEL_CONTROL_ADDR_INPUT_CHANNELS_DATA       0x94
#define XPOSE_CNN_ACCEL_CONTROL_BITS_INPUT_CHANNELS_DATA       32
#define XPOSE_CNN_ACCEL_CONTROL_ADDR_OUTPUT_CHANNELS_DATA      0x9c
#define XPOSE_CNN_ACCEL_CONTROL_BITS_OUTPUT_CHANNELS_DATA      32
#define XPOSE_CNN_ACCEL_CONTROL_ADDR_STRIDE_DATA               0xa4
#define XPOSE_CNN_ACCEL_CONTROL_BITS_STRIDE_DATA               32
#define XPOSE_CNN_ACCEL_CONTROL_ADDR_INPUT_ZERO_POINT_DATA     0xac
#define XPOSE_CNN_ACCEL_CONTROL_BITS_INPUT_ZERO_POINT_DATA     32
#define XPOSE_CNN_ACCEL_CONTROL_ADDR_DW_OUTPUT_ZERO_POINT_DATA 0xb4
#define XPOSE_CNN_ACCEL_CONTROL_BITS_DW_OUTPUT_ZERO_POINT_DATA 32
#define XPOSE_CNN_ACCEL_CONTROL_ADDR_OUTPUT_ZERO_POINT_DATA    0xbc
#define XPOSE_CNN_ACCEL_CONTROL_BITS_OUTPUT_ZERO_POINT_DATA    32
#define XPOSE_CNN_ACCEL_CONTROL_ADDR_RESIDUAL_ZERO_POINT_DATA  0xc4
#define XPOSE_CNN_ACCEL_CONTROL_BITS_RESIDUAL_ZERO_POINT_DATA  32
#define XPOSE_CNN_ACCEL_CONTROL_ADDR_RESIDUAL_MULTIPLIER_DATA  0xcc
#define XPOSE_CNN_ACCEL_CONTROL_BITS_RESIDUAL_MULTIPLIER_DATA  32
#define XPOSE_CNN_ACCEL_CONTROL_ADDR_RESIDUAL_SHIFT_DATA       0xd4
#define XPOSE_CNN_ACCEL_CONTROL_BITS_RESIDUAL_SHIFT_DATA       32
#define XPOSE_CNN_ACCEL_CONTROL_ADDR_RELU_ENABLE_DATA          0xdc
#define XPOSE_CNN_ACCEL_CONTROL_BITS_RELU_ENABLE_DATA          32
#define XPOSE_CNN_ACCEL_CONTROL_ADDR_RESIDUAL_ENABLE_DATA      0xe4
#define XPOSE_CNN_ACCEL_CONTROL_BITS_RESIDUAL_ENABLE_DATA      32

