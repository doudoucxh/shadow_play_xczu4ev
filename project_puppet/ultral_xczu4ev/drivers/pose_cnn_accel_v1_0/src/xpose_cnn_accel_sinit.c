// ==============================================================
// Vitis HLS - High-Level Synthesis from C, C++ and OpenCL v2022.2 (64-bit)
// Tool Version Limit: 2019.12
// Copyright 1986-2022 Xilinx, Inc. All Rights Reserved.
// ==============================================================
#ifndef __linux__

#include "xstatus.h"
#include "xparameters.h"
#include "xpose_cnn_accel.h"

extern XPose_cnn_accel_Config XPose_cnn_accel_ConfigTable[];

XPose_cnn_accel_Config *XPose_cnn_accel_LookupConfig(u16 DeviceId) {
	XPose_cnn_accel_Config *ConfigPtr = NULL;

	int Index;

	for (Index = 0; Index < XPAR_XPOSE_CNN_ACCEL_NUM_INSTANCES; Index++) {
		if (XPose_cnn_accel_ConfigTable[Index].DeviceId == DeviceId) {
			ConfigPtr = &XPose_cnn_accel_ConfigTable[Index];
			break;
		}
	}

	return ConfigPtr;
}

int XPose_cnn_accel_Initialize(XPose_cnn_accel *InstancePtr, u16 DeviceId) {
	XPose_cnn_accel_Config *ConfigPtr;

	Xil_AssertNonvoid(InstancePtr != NULL);

	ConfigPtr = XPose_cnn_accel_LookupConfig(DeviceId);
	if (ConfigPtr == NULL) {
		InstancePtr->IsReady = 0;
		return (XST_DEVICE_NOT_FOUND);
	}

	return XPose_cnn_accel_CfgInitialize(InstancePtr, ConfigPtr);
}

#endif

