// ==============================================================
// Vitis HLS - High-Level Synthesis from C, C++ and OpenCL v2022.2 (64-bit)
// Tool Version Limit: 2019.12
// Copyright 1986-2022 Xilinx, Inc. All Rights Reserved.
// ==============================================================
/***************************** Include Files *********************************/
#include "xpose_cnn_accel.h"

/************************** Function Implementation *************************/
#ifndef __linux__
int XPose_cnn_accel_CfgInitialize(XPose_cnn_accel *InstancePtr, XPose_cnn_accel_Config *ConfigPtr) {
    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(ConfigPtr != NULL);

    InstancePtr->Control_BaseAddress = ConfigPtr->Control_BaseAddress;
    InstancePtr->IsReady = XIL_COMPONENT_IS_READY;

    return XST_SUCCESS;
}
#endif

void XPose_cnn_accel_Start(XPose_cnn_accel *InstancePtr) {
    u32 Data;

    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XPose_cnn_accel_ReadReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_AP_CTRL) & 0x80;
    XPose_cnn_accel_WriteReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_AP_CTRL, Data | 0x01);
}

u32 XPose_cnn_accel_IsDone(XPose_cnn_accel *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XPose_cnn_accel_ReadReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_AP_CTRL);
    return (Data >> 1) & 0x1;
}

u32 XPose_cnn_accel_IsIdle(XPose_cnn_accel *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XPose_cnn_accel_ReadReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_AP_CTRL);
    return (Data >> 2) & 0x1;
}

u32 XPose_cnn_accel_IsReady(XPose_cnn_accel *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XPose_cnn_accel_ReadReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_AP_CTRL);
    // check ap_start to see if the pcore is ready for next input
    return !(Data & 0x1);
}

void XPose_cnn_accel_EnableAutoRestart(XPose_cnn_accel *InstancePtr) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XPose_cnn_accel_WriteReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_AP_CTRL, 0x80);
}

void XPose_cnn_accel_DisableAutoRestart(XPose_cnn_accel *InstancePtr) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XPose_cnn_accel_WriteReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_AP_CTRL, 0);
}

void XPose_cnn_accel_Set_input_raw(XPose_cnn_accel *InstancePtr, u64 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XPose_cnn_accel_WriteReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_INPUT_RAW_DATA, (u32)(Data));
    XPose_cnn_accel_WriteReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_INPUT_RAW_DATA + 4, (u32)(Data >> 32));
}

u64 XPose_cnn_accel_Get_input_raw(XPose_cnn_accel *InstancePtr) {
    u64 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XPose_cnn_accel_ReadReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_INPUT_RAW_DATA);
    Data += (u64)XPose_cnn_accel_ReadReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_INPUT_RAW_DATA + 4) << 32;
    return Data;
}

void XPose_cnn_accel_Set_input_r(XPose_cnn_accel *InstancePtr, u64 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XPose_cnn_accel_WriteReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_INPUT_R_DATA, (u32)(Data));
    XPose_cnn_accel_WriteReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_INPUT_R_DATA + 4, (u32)(Data >> 32));
}

u64 XPose_cnn_accel_Get_input_r(XPose_cnn_accel *InstancePtr) {
    u64 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XPose_cnn_accel_ReadReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_INPUT_R_DATA);
    Data += (u64)XPose_cnn_accel_ReadReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_INPUT_R_DATA + 4) << 32;
    return Data;
}

void XPose_cnn_accel_Set_input_lut(XPose_cnn_accel *InstancePtr, u64 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XPose_cnn_accel_WriteReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_INPUT_LUT_DATA, (u32)(Data));
    XPose_cnn_accel_WriteReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_INPUT_LUT_DATA + 4, (u32)(Data >> 32));
}

u64 XPose_cnn_accel_Get_input_lut(XPose_cnn_accel *InstancePtr) {
    u64 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XPose_cnn_accel_ReadReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_INPUT_LUT_DATA);
    Data += (u64)XPose_cnn_accel_ReadReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_INPUT_LUT_DATA + 4) << 32;
    return Data;
}

void XPose_cnn_accel_Set_dw_weights(XPose_cnn_accel *InstancePtr, u64 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XPose_cnn_accel_WriteReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_DW_WEIGHTS_DATA, (u32)(Data));
    XPose_cnn_accel_WriteReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_DW_WEIGHTS_DATA + 4, (u32)(Data >> 32));
}

u64 XPose_cnn_accel_Get_dw_weights(XPose_cnn_accel *InstancePtr) {
    u64 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XPose_cnn_accel_ReadReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_DW_WEIGHTS_DATA);
    Data += (u64)XPose_cnn_accel_ReadReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_DW_WEIGHTS_DATA + 4) << 32;
    return Data;
}

void XPose_cnn_accel_Set_dw_params(XPose_cnn_accel *InstancePtr, u64 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XPose_cnn_accel_WriteReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_DW_PARAMS_DATA, (u32)(Data));
    XPose_cnn_accel_WriteReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_DW_PARAMS_DATA + 4, (u32)(Data >> 32));
}

u64 XPose_cnn_accel_Get_dw_params(XPose_cnn_accel *InstancePtr) {
    u64 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XPose_cnn_accel_ReadReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_DW_PARAMS_DATA);
    Data += (u64)XPose_cnn_accel_ReadReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_DW_PARAMS_DATA + 4) << 32;
    return Data;
}

void XPose_cnn_accel_Set_pw_weights(XPose_cnn_accel *InstancePtr, u64 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XPose_cnn_accel_WriteReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_PW_WEIGHTS_DATA, (u32)(Data));
    XPose_cnn_accel_WriteReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_PW_WEIGHTS_DATA + 4, (u32)(Data >> 32));
}

u64 XPose_cnn_accel_Get_pw_weights(XPose_cnn_accel *InstancePtr) {
    u64 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XPose_cnn_accel_ReadReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_PW_WEIGHTS_DATA);
    Data += (u64)XPose_cnn_accel_ReadReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_PW_WEIGHTS_DATA + 4) << 32;
    return Data;
}

void XPose_cnn_accel_Set_pw_params(XPose_cnn_accel *InstancePtr, u64 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XPose_cnn_accel_WriteReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_PW_PARAMS_DATA, (u32)(Data));
    XPose_cnn_accel_WriteReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_PW_PARAMS_DATA + 4, (u32)(Data >> 32));
}

u64 XPose_cnn_accel_Get_pw_params(XPose_cnn_accel *InstancePtr) {
    u64 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XPose_cnn_accel_ReadReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_PW_PARAMS_DATA);
    Data += (u64)XPose_cnn_accel_ReadReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_PW_PARAMS_DATA + 4) << 32;
    return Data;
}

void XPose_cnn_accel_Set_residual(XPose_cnn_accel *InstancePtr, u64 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XPose_cnn_accel_WriteReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_RESIDUAL_DATA, (u32)(Data));
    XPose_cnn_accel_WriteReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_RESIDUAL_DATA + 4, (u32)(Data >> 32));
}

u64 XPose_cnn_accel_Get_residual(XPose_cnn_accel *InstancePtr) {
    u64 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XPose_cnn_accel_ReadReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_RESIDUAL_DATA);
    Data += (u64)XPose_cnn_accel_ReadReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_RESIDUAL_DATA + 4) << 32;
    return Data;
}

void XPose_cnn_accel_Set_output_r(XPose_cnn_accel *InstancePtr, u64 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XPose_cnn_accel_WriteReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_OUTPUT_R_DATA, (u32)(Data));
    XPose_cnn_accel_WriteReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_OUTPUT_R_DATA + 4, (u32)(Data >> 32));
}

u64 XPose_cnn_accel_Get_output_r(XPose_cnn_accel *InstancePtr) {
    u64 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XPose_cnn_accel_ReadReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_OUTPUT_R_DATA);
    Data += (u64)XPose_cnn_accel_ReadReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_OUTPUT_R_DATA + 4) << 32;
    return Data;
}

void XPose_cnn_accel_Set_operation(XPose_cnn_accel *InstancePtr, u32 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XPose_cnn_accel_WriteReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_OPERATION_DATA, Data);
}

u32 XPose_cnn_accel_Get_operation(XPose_cnn_accel *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XPose_cnn_accel_ReadReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_OPERATION_DATA);
    return Data;
}

void XPose_cnn_accel_Set_height(XPose_cnn_accel *InstancePtr, u32 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XPose_cnn_accel_WriteReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_HEIGHT_DATA, Data);
}

u32 XPose_cnn_accel_Get_height(XPose_cnn_accel *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XPose_cnn_accel_ReadReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_HEIGHT_DATA);
    return Data;
}

void XPose_cnn_accel_Set_width(XPose_cnn_accel *InstancePtr, u32 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XPose_cnn_accel_WriteReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_WIDTH_DATA, Data);
}

u32 XPose_cnn_accel_Get_width(XPose_cnn_accel *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XPose_cnn_accel_ReadReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_WIDTH_DATA);
    return Data;
}

void XPose_cnn_accel_Set_input_channels(XPose_cnn_accel *InstancePtr, u32 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XPose_cnn_accel_WriteReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_INPUT_CHANNELS_DATA, Data);
}

u32 XPose_cnn_accel_Get_input_channels(XPose_cnn_accel *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XPose_cnn_accel_ReadReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_INPUT_CHANNELS_DATA);
    return Data;
}

void XPose_cnn_accel_Set_output_channels(XPose_cnn_accel *InstancePtr, u32 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XPose_cnn_accel_WriteReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_OUTPUT_CHANNELS_DATA, Data);
}

u32 XPose_cnn_accel_Get_output_channels(XPose_cnn_accel *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XPose_cnn_accel_ReadReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_OUTPUT_CHANNELS_DATA);
    return Data;
}

void XPose_cnn_accel_Set_stride(XPose_cnn_accel *InstancePtr, u32 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XPose_cnn_accel_WriteReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_STRIDE_DATA, Data);
}

u32 XPose_cnn_accel_Get_stride(XPose_cnn_accel *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XPose_cnn_accel_ReadReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_STRIDE_DATA);
    return Data;
}

void XPose_cnn_accel_Set_input_zero_point(XPose_cnn_accel *InstancePtr, u32 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XPose_cnn_accel_WriteReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_INPUT_ZERO_POINT_DATA, Data);
}

u32 XPose_cnn_accel_Get_input_zero_point(XPose_cnn_accel *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XPose_cnn_accel_ReadReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_INPUT_ZERO_POINT_DATA);
    return Data;
}

void XPose_cnn_accel_Set_dw_output_zero_point(XPose_cnn_accel *InstancePtr, u32 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XPose_cnn_accel_WriteReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_DW_OUTPUT_ZERO_POINT_DATA, Data);
}

u32 XPose_cnn_accel_Get_dw_output_zero_point(XPose_cnn_accel *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XPose_cnn_accel_ReadReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_DW_OUTPUT_ZERO_POINT_DATA);
    return Data;
}

void XPose_cnn_accel_Set_output_zero_point(XPose_cnn_accel *InstancePtr, u32 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XPose_cnn_accel_WriteReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_OUTPUT_ZERO_POINT_DATA, Data);
}

u32 XPose_cnn_accel_Get_output_zero_point(XPose_cnn_accel *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XPose_cnn_accel_ReadReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_OUTPUT_ZERO_POINT_DATA);
    return Data;
}

void XPose_cnn_accel_Set_residual_zero_point(XPose_cnn_accel *InstancePtr, u32 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XPose_cnn_accel_WriteReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_RESIDUAL_ZERO_POINT_DATA, Data);
}

u32 XPose_cnn_accel_Get_residual_zero_point(XPose_cnn_accel *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XPose_cnn_accel_ReadReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_RESIDUAL_ZERO_POINT_DATA);
    return Data;
}

void XPose_cnn_accel_Set_residual_multiplier(XPose_cnn_accel *InstancePtr, u32 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XPose_cnn_accel_WriteReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_RESIDUAL_MULTIPLIER_DATA, Data);
}

u32 XPose_cnn_accel_Get_residual_multiplier(XPose_cnn_accel *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XPose_cnn_accel_ReadReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_RESIDUAL_MULTIPLIER_DATA);
    return Data;
}

void XPose_cnn_accel_Set_residual_shift(XPose_cnn_accel *InstancePtr, u32 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XPose_cnn_accel_WriteReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_RESIDUAL_SHIFT_DATA, Data);
}

u32 XPose_cnn_accel_Get_residual_shift(XPose_cnn_accel *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XPose_cnn_accel_ReadReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_RESIDUAL_SHIFT_DATA);
    return Data;
}

void XPose_cnn_accel_Set_relu_enable(XPose_cnn_accel *InstancePtr, u32 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XPose_cnn_accel_WriteReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_RELU_ENABLE_DATA, Data);
}

u32 XPose_cnn_accel_Get_relu_enable(XPose_cnn_accel *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XPose_cnn_accel_ReadReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_RELU_ENABLE_DATA);
    return Data;
}

void XPose_cnn_accel_Set_residual_enable(XPose_cnn_accel *InstancePtr, u32 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XPose_cnn_accel_WriteReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_RESIDUAL_ENABLE_DATA, Data);
}

u32 XPose_cnn_accel_Get_residual_enable(XPose_cnn_accel *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XPose_cnn_accel_ReadReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_RESIDUAL_ENABLE_DATA);
    return Data;
}

void XPose_cnn_accel_InterruptGlobalEnable(XPose_cnn_accel *InstancePtr) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XPose_cnn_accel_WriteReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_GIE, 1);
}

void XPose_cnn_accel_InterruptGlobalDisable(XPose_cnn_accel *InstancePtr) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XPose_cnn_accel_WriteReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_GIE, 0);
}

void XPose_cnn_accel_InterruptEnable(XPose_cnn_accel *InstancePtr, u32 Mask) {
    u32 Register;

    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Register =  XPose_cnn_accel_ReadReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_IER);
    XPose_cnn_accel_WriteReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_IER, Register | Mask);
}

void XPose_cnn_accel_InterruptDisable(XPose_cnn_accel *InstancePtr, u32 Mask) {
    u32 Register;

    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Register =  XPose_cnn_accel_ReadReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_IER);
    XPose_cnn_accel_WriteReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_IER, Register & (~Mask));
}

void XPose_cnn_accel_InterruptClear(XPose_cnn_accel *InstancePtr, u32 Mask) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XPose_cnn_accel_WriteReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_ISR, Mask);
}

u32 XPose_cnn_accel_InterruptGetEnabled(XPose_cnn_accel *InstancePtr) {
    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    return XPose_cnn_accel_ReadReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_IER);
}

u32 XPose_cnn_accel_InterruptGetStatus(XPose_cnn_accel *InstancePtr) {
    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    return XPose_cnn_accel_ReadReg(InstancePtr->Control_BaseAddress, XPOSE_CNN_ACCEL_CONTROL_ADDR_ISR);
}

