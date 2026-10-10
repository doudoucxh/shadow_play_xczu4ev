// ==============================================================
// Vitis HLS - High-Level Synthesis from C, C++ and OpenCL v2022.2 (64-bit)
// Tool Version Limit: 2019.12
// Copyright 1986-2022 Xilinx, Inc. All Rights Reserved.
// ==============================================================
#ifndef XPOSE_CNN_ACCEL_H
#define XPOSE_CNN_ACCEL_H

#ifdef __cplusplus
extern "C" {
#endif

/***************************** Include Files *********************************/
#ifndef __linux__
#include "xil_types.h"
#include "xil_assert.h"
#include "xstatus.h"
#include "xil_io.h"
#else
#include <stdint.h>
#include <assert.h>
#include <dirent.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
#include <stddef.h>
#endif
#include "xpose_cnn_accel_hw.h"

/**************************** Type Definitions ******************************/
#ifdef __linux__
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef uint64_t u64;
#else
typedef struct {
    u16 DeviceId;
    u64 Control_BaseAddress;
} XPose_cnn_accel_Config;
#endif

typedef struct {
    u64 Control_BaseAddress;
    u32 IsReady;
} XPose_cnn_accel;

typedef u32 word_type;

/***************** Macros (Inline Functions) Definitions *********************/
#ifndef __linux__
#define XPose_cnn_accel_WriteReg(BaseAddress, RegOffset, Data) \
    Xil_Out32((BaseAddress) + (RegOffset), (u32)(Data))
#define XPose_cnn_accel_ReadReg(BaseAddress, RegOffset) \
    Xil_In32((BaseAddress) + (RegOffset))
#else
#define XPose_cnn_accel_WriteReg(BaseAddress, RegOffset, Data) \
    *(volatile u32*)((BaseAddress) + (RegOffset)) = (u32)(Data)
#define XPose_cnn_accel_ReadReg(BaseAddress, RegOffset) \
    *(volatile u32*)((BaseAddress) + (RegOffset))

#define Xil_AssertVoid(expr)    assert(expr)
#define Xil_AssertNonvoid(expr) assert(expr)

#define XST_SUCCESS             0
#define XST_DEVICE_NOT_FOUND    2
#define XST_OPEN_DEVICE_FAILED  3
#define XIL_COMPONENT_IS_READY  1
#endif

/************************** Function Prototypes *****************************/
#ifndef __linux__
int XPose_cnn_accel_Initialize(XPose_cnn_accel *InstancePtr, u16 DeviceId);
XPose_cnn_accel_Config* XPose_cnn_accel_LookupConfig(u16 DeviceId);
int XPose_cnn_accel_CfgInitialize(XPose_cnn_accel *InstancePtr, XPose_cnn_accel_Config *ConfigPtr);
#else
int XPose_cnn_accel_Initialize(XPose_cnn_accel *InstancePtr, const char* InstanceName);
int XPose_cnn_accel_Release(XPose_cnn_accel *InstancePtr);
#endif

void XPose_cnn_accel_Start(XPose_cnn_accel *InstancePtr);
u32 XPose_cnn_accel_IsDone(XPose_cnn_accel *InstancePtr);
u32 XPose_cnn_accel_IsIdle(XPose_cnn_accel *InstancePtr);
u32 XPose_cnn_accel_IsReady(XPose_cnn_accel *InstancePtr);
void XPose_cnn_accel_EnableAutoRestart(XPose_cnn_accel *InstancePtr);
void XPose_cnn_accel_DisableAutoRestart(XPose_cnn_accel *InstancePtr);

void XPose_cnn_accel_Set_input_raw(XPose_cnn_accel *InstancePtr, u64 Data);
u64 XPose_cnn_accel_Get_input_raw(XPose_cnn_accel *InstancePtr);
void XPose_cnn_accel_Set_input_r(XPose_cnn_accel *InstancePtr, u64 Data);
u64 XPose_cnn_accel_Get_input_r(XPose_cnn_accel *InstancePtr);
void XPose_cnn_accel_Set_input_lut(XPose_cnn_accel *InstancePtr, u64 Data);
u64 XPose_cnn_accel_Get_input_lut(XPose_cnn_accel *InstancePtr);
void XPose_cnn_accel_Set_dw_weights(XPose_cnn_accel *InstancePtr, u64 Data);
u64 XPose_cnn_accel_Get_dw_weights(XPose_cnn_accel *InstancePtr);
void XPose_cnn_accel_Set_dw_params(XPose_cnn_accel *InstancePtr, u64 Data);
u64 XPose_cnn_accel_Get_dw_params(XPose_cnn_accel *InstancePtr);
void XPose_cnn_accel_Set_pw_weights(XPose_cnn_accel *InstancePtr, u64 Data);
u64 XPose_cnn_accel_Get_pw_weights(XPose_cnn_accel *InstancePtr);
void XPose_cnn_accel_Set_pw_params(XPose_cnn_accel *InstancePtr, u64 Data);
u64 XPose_cnn_accel_Get_pw_params(XPose_cnn_accel *InstancePtr);
void XPose_cnn_accel_Set_residual(XPose_cnn_accel *InstancePtr, u64 Data);
u64 XPose_cnn_accel_Get_residual(XPose_cnn_accel *InstancePtr);
void XPose_cnn_accel_Set_output_r(XPose_cnn_accel *InstancePtr, u64 Data);
u64 XPose_cnn_accel_Get_output_r(XPose_cnn_accel *InstancePtr);
void XPose_cnn_accel_Set_operation(XPose_cnn_accel *InstancePtr, u32 Data);
u32 XPose_cnn_accel_Get_operation(XPose_cnn_accel *InstancePtr);
void XPose_cnn_accel_Set_height(XPose_cnn_accel *InstancePtr, u32 Data);
u32 XPose_cnn_accel_Get_height(XPose_cnn_accel *InstancePtr);
void XPose_cnn_accel_Set_width(XPose_cnn_accel *InstancePtr, u32 Data);
u32 XPose_cnn_accel_Get_width(XPose_cnn_accel *InstancePtr);
void XPose_cnn_accel_Set_input_channels(XPose_cnn_accel *InstancePtr, u32 Data);
u32 XPose_cnn_accel_Get_input_channels(XPose_cnn_accel *InstancePtr);
void XPose_cnn_accel_Set_output_channels(XPose_cnn_accel *InstancePtr, u32 Data);
u32 XPose_cnn_accel_Get_output_channels(XPose_cnn_accel *InstancePtr);
void XPose_cnn_accel_Set_stride(XPose_cnn_accel *InstancePtr, u32 Data);
u32 XPose_cnn_accel_Get_stride(XPose_cnn_accel *InstancePtr);
void XPose_cnn_accel_Set_input_zero_point(XPose_cnn_accel *InstancePtr, u32 Data);
u32 XPose_cnn_accel_Get_input_zero_point(XPose_cnn_accel *InstancePtr);
void XPose_cnn_accel_Set_dw_output_zero_point(XPose_cnn_accel *InstancePtr, u32 Data);
u32 XPose_cnn_accel_Get_dw_output_zero_point(XPose_cnn_accel *InstancePtr);
void XPose_cnn_accel_Set_output_zero_point(XPose_cnn_accel *InstancePtr, u32 Data);
u32 XPose_cnn_accel_Get_output_zero_point(XPose_cnn_accel *InstancePtr);
void XPose_cnn_accel_Set_residual_zero_point(XPose_cnn_accel *InstancePtr, u32 Data);
u32 XPose_cnn_accel_Get_residual_zero_point(XPose_cnn_accel *InstancePtr);
void XPose_cnn_accel_Set_residual_multiplier(XPose_cnn_accel *InstancePtr, u32 Data);
u32 XPose_cnn_accel_Get_residual_multiplier(XPose_cnn_accel *InstancePtr);
void XPose_cnn_accel_Set_residual_shift(XPose_cnn_accel *InstancePtr, u32 Data);
u32 XPose_cnn_accel_Get_residual_shift(XPose_cnn_accel *InstancePtr);
void XPose_cnn_accel_Set_relu_enable(XPose_cnn_accel *InstancePtr, u32 Data);
u32 XPose_cnn_accel_Get_relu_enable(XPose_cnn_accel *InstancePtr);
void XPose_cnn_accel_Set_residual_enable(XPose_cnn_accel *InstancePtr, u32 Data);
u32 XPose_cnn_accel_Get_residual_enable(XPose_cnn_accel *InstancePtr);

void XPose_cnn_accel_InterruptGlobalEnable(XPose_cnn_accel *InstancePtr);
void XPose_cnn_accel_InterruptGlobalDisable(XPose_cnn_accel *InstancePtr);
void XPose_cnn_accel_InterruptEnable(XPose_cnn_accel *InstancePtr, u32 Mask);
void XPose_cnn_accel_InterruptDisable(XPose_cnn_accel *InstancePtr, u32 Mask);
void XPose_cnn_accel_InterruptClear(XPose_cnn_accel *InstancePtr, u32 Mask);
u32 XPose_cnn_accel_InterruptGetEnabled(XPose_cnn_accel *InstancePtr);
u32 XPose_cnn_accel_InterruptGetStatus(XPose_cnn_accel *InstancePtr);

#ifdef __cplusplus
}
#endif

#endif
