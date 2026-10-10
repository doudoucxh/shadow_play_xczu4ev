#ifndef POSE_PW_ACCEL_TEST_H
#define POSE_PW_ACCEL_TEST_H

#include <string.h>

#include "xil_cache.h"
#include "xil_io.h"
#include "xil_printf.h"
#include "xparameters.h"
#include "xtime_l.h"

#ifndef XPAR_POSE_PW_ACCEL_0_S_AXI_CONTROL_BASEADDR
#define XPAR_POSE_PW_ACCEL_0_S_AXI_CONTROL_BASEADDR 0x43C00000U
#endif

#define POSE_PW_TEST_MAGIC_ADDR 0x02200100U
#define POSE_PW_TEST_MAGIC 0x50574143U
#define POSE_PW_TEST_INPUT_ADDR 0x02400000U
#define POSE_PW_TEST_WEIGHT_ADDR 0x02420000U
#define POSE_PW_TEST_BIAS_ADDR 0x02421000U
#define POSE_PW_TEST_OUTPUT_ADDR 0x02422000U
#define POSE_PW_TEST_REFERENCE_ADDR 0x02490000U

#define POSE_PW_REG_CONTROL 0x00U
#define POSE_PW_REG_INPUT 0x10U
#define POSE_PW_REG_WEIGHTS 0x1CU
#define POSE_PW_REG_BIAS 0x28U
#define POSE_PW_REG_OUTPUT 0x34U
#define POSE_PW_REG_PIXELS 0x40U
#define POSE_PW_REG_INPUT_CHANNELS 0x48U
#define POSE_PW_REG_OUTPUT_CHANNELS 0x50U

typedef struct {
    u32 magic;
    u32 version;
    u32 elapsed_us;
    u32 mismatches;
    u32 maximum_delta;
    u32 control_base;
    s32 reference_sample;
    s32 hardware_sample;
    u32 cpu_elapsed_us;
    u32 speedup_milli;
} PosePwHardwareTestResult;

static void pose_pw_write_pointer(u32 base, u32 offset, UINTPTR address)
{
    Xil_Out32(base + offset, (u32)address);
    Xil_Out32(base + offset + 4U, 0U);
}

static int pose_pw_accel_self_test(void)
{
    enum { pixels = 64 * 36, input_channels = 32, output_channels = 48 };
    volatile s8 *input = (volatile s8 *)POSE_PW_TEST_INPUT_ADDR;
    volatile s8 *weights = (volatile s8 *)POSE_PW_TEST_WEIGHT_ADDR;
    volatile s32 *bias = (volatile s32 *)POSE_PW_TEST_BIAS_ADDR;
    volatile s32 *output = (volatile s32 *)POSE_PW_TEST_OUTPUT_ADDR;
    volatile s32 *reference_output =
        (volatile s32 *)POSE_PW_TEST_REFERENCE_ADDR;
    volatile PosePwHardwareTestResult *result =
        (volatile PosePwHardwareTestResult *)POSE_PW_TEST_MAGIC_ADDR;
    const u32 base = XPAR_POSE_PW_ACCEL_0_S_AXI_CONTROL_BASEADDR;
    u32 pixel, oc, ic, timeout = 0U;
    u32 mismatches = 0U, maximum_delta = 0U;
    XTime start, end, cpu_start, cpu_end;

    result->magic = 0U;
    Xil_DCacheFlushRange(POSE_PW_TEST_MAGIC_ADDR, sizeof(*result));
    for (pixel = 0; pixel < pixels; ++pixel)
        for (ic = 0; ic < input_channels; ++ic)
            input[pixel * input_channels + ic] =
                (s8)((s32)((pixel * 13U + ic * 7U + 19U) % 31U) - 15);
    for (oc = 0; oc < output_channels; ++oc) {
        bias[oc] = (s32)oc * 17 - 301;
        for (ic = 0; ic < input_channels; ++ic)
            weights[oc * input_channels + ic] =
                (s8)((s32)((oc * 11U + ic * 5U + 3U) % 23U) - 11);
    }
    memset((void *)output, 0, pixels * output_channels * sizeof(s32));
    Xil_DCacheFlushRange(POSE_PW_TEST_INPUT_ADDR, pixels * input_channels);
    Xil_DCacheFlushRange(POSE_PW_TEST_WEIGHT_ADDR,
                         output_channels * input_channels);
    Xil_DCacheFlushRange(POSE_PW_TEST_BIAS_ADDR,
                         output_channels * sizeof(s32));
    Xil_DCacheFlushRange(POSE_PW_TEST_OUTPUT_ADDR,
                         pixels * output_channels * sizeof(s32));

    pose_pw_write_pointer(base, POSE_PW_REG_INPUT, POSE_PW_TEST_INPUT_ADDR);
    pose_pw_write_pointer(base, POSE_PW_REG_WEIGHTS, POSE_PW_TEST_WEIGHT_ADDR);
    pose_pw_write_pointer(base, POSE_PW_REG_BIAS, POSE_PW_TEST_BIAS_ADDR);
    pose_pw_write_pointer(base, POSE_PW_REG_OUTPUT, POSE_PW_TEST_OUTPUT_ADDR);
    Xil_Out32(base + POSE_PW_REG_PIXELS, pixels);
    Xil_Out32(base + POSE_PW_REG_INPUT_CHANNELS, input_channels);
    Xil_Out32(base + POSE_PW_REG_OUTPUT_CHANNELS, output_channels);
    XTime_GetTime(&start);
    Xil_Out32(base + POSE_PW_REG_CONTROL, 1U);
    while ((Xil_In32(base + POSE_PW_REG_CONTROL) & 0x2U) == 0U) {
        if (++timeout > 100000000U) {
            xil_printf("POSE_PW_PL_TEST timeout ctrl=0x%08x\r\n",
                       Xil_In32(base + POSE_PW_REG_CONTROL));
            return -1;
        }
    }
    XTime_GetTime(&end);
    Xil_DCacheInvalidateRange(POSE_PW_TEST_OUTPUT_ADDR,
                              pixels * output_channels * sizeof(s32));

    Xil_DCacheInvalidateRange(POSE_PW_TEST_INPUT_ADDR,
                              pixels * input_channels);
    Xil_DCacheInvalidateRange(POSE_PW_TEST_WEIGHT_ADDR,
                              output_channels * input_channels);
    Xil_DCacheInvalidateRange(POSE_PW_TEST_BIAS_ADDR,
                              output_channels * sizeof(s32));
    XTime_GetTime(&cpu_start);
    for (pixel = 0; pixel < pixels; ++pixel) {
        for (oc = 0; oc < output_channels; ++oc) {
            s32 reference = bias[oc];
            for (ic = 0; ic < input_channels; ++ic)
                reference += (s32)input[pixel * input_channels + ic] *
                             (s32)weights[oc * input_channels + ic];
            reference_output[pixel * output_channels + oc] = reference;
        }
    }
    XTime_GetTime(&cpu_end);

    for (pixel = 0; pixel < pixels; ++pixel) {
        for (oc = 0; oc < output_channels; ++oc) {
            s32 delta = output[pixel * output_channels + oc] -
                        reference_output[pixel * output_channels + oc];
            if (delta < 0)
                delta = -delta;
            if ((u32)delta > maximum_delta)
                maximum_delta = (u32)delta;
            if (delta != 0)
                ++mismatches;
        }
    }
    result->version = 2U;
    result->elapsed_us = (u32)(((end - start) * 1000000ULL) /
                               COUNTS_PER_SECOND);
    result->mismatches = mismatches;
    result->maximum_delta = maximum_delta;
    result->control_base = base;
    result->reference_sample = reference_output[0];
    result->hardware_sample = output[0];
    result->cpu_elapsed_us = (u32)(((cpu_end - cpu_start) * 1000000ULL) /
                                   COUNTS_PER_SECOND);
    result->speedup_milli = result->elapsed_us == 0U ? 0U :
        (result->cpu_elapsed_us * 1000U) / result->elapsed_us;
    result->magic = POSE_PW_TEST_MAGIC;
    Xil_DCacheFlushRange(POSE_PW_TEST_MAGIC_ADDR, sizeof(*result));
    xil_printf("POSE_PW_PL_TEST mismatches=%d max_delta=%d pl_us=%d cpu_us=%d speedup_x1000=%d\r\n",
               mismatches, maximum_delta, result->elapsed_us,
               result->cpu_elapsed_us, result->speedup_milli);
    return mismatches == 0U ? 0 : -1;
}

#endif
