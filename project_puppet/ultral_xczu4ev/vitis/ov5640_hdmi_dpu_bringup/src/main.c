/* DPU hardware bring-up only: OV5640 -> VDMA -> HDMI, plus a DPU AXI probe. */
#include "xparameters.h"
#include "xstatus.h"
#include "xil_io.h"
#include "xil_printf.h"
#include "sleep.h"
#include "display_ctrl_hdmi/display_ctrl_hdmi.h"
#include "vdma_api/vdma_api.h"
#include "emio_sccb_cfg/emio_sccb_cfg.h"
#include "ov5640/ov5640_init.h"

#if defined(XPAR_PSU_DDR_0_S_AXI_BASEADDR)
#define DDR_BASE_ADDR XPAR_PSU_DDR_0_S_AXI_BASEADDR
#elif defined(XPAR_PSU_DDR_0_BASEADDRESS)
#define DDR_BASE_ADDR XPAR_PSU_DDR_0_BASEADDRESS
#else
#define DDR_BASE_ADDR 0x00000000U
#endif

#if defined(XPAR_DPU_0_BASEADDR)
#define DPU_BASE_ADDR ((UINTPTR)XPAR_DPU_0_BASEADDR)
#elif defined(XPAR_DPUCZDX8G_0_BASEADDR)
#define DPU_BASE_ADDR ((UINTPTR)XPAR_DPUCZDX8G_0_BASEADDR)
#else
#error "DPU base address is missing from xparameters.h"
#endif

#define FRAME_BUFFER_ADDR (DDR_BASE_ADDR + 0x01000000U)
#define POSE_BUFFER_ADDR  (DDR_BASE_ADDR + 0x02000000U)
#define CAMERA_WIDTH       1280U
#define CAMERA_HEIGHT       720U
#define CAMERA_TOTAL_WIDTH 2570U
#define CAMERA_TOTAL_HEIGHT 980U
#define POSE_WIDTH           256U
#define POSE_HEIGHT          144U

static XAxiVdma video_vdma;
static XAxiVdma pose_vdma;
static DisplayCtrl display;

extern void sccb_write_reg16(u16 addr, u8 data);

static void print_dpu_probe(void)
{
    u64 address = (u64)DPU_BASE_ADDR;
    u32 register0 = Xil_In32(DPU_BASE_ADDR);

    xil_printf("DPU AXI base: 0x%08x%08x\r\n",
               (u32)(address >> 32), (u32)address);
    xil_printf("DPU register[0x0000]: 0x%08x\r\n", register0);
    xil_printf("DPU AXI probe passed; inference is intentionally disabled.\r\n");
}

int main(void)
{
    int status;

    xil_printf("\r\nShadow DPU logic bring-up: camera + preprocessing + HDMI\r\n");
    xil_printf("This build does not run a pose model.\r\n");

    emio_init();
    status = ov5640_init(CAMERA_WIDTH, CAMERA_HEIGHT,
                         CAMERA_TOTAL_WIDTH, CAMERA_TOTAL_HEIGHT);
    if (status != 0) {
        xil_printf("OV5640 detection failed; check power, connector and SCCB.\r\n");
        return XST_FAILURE;
    }
    sccb_write_reg16(0x3820U, 0x40U);
    xil_printf("OV5640 detected and configured for 1280x720.\r\n");

    status = run_vdma_frame_buffer(&video_vdma, XPAR_AXIVDMA_0_DEVICE_ID,
                                   CAMERA_WIDTH, CAMERA_HEIGHT,
                                   FRAME_BUFFER_ADDR, 0, 0, BOTH);
    if (status != XST_SUCCESS) {
        xil_printf("Video VDMA initialization failed: %d\r\n", status);
        return XST_FAILURE;
    }

    status = DisplayInitialize(&display, XPAR_VTC_0_DEVICE_ID);
    if (status == XST_SUCCESS)
        status = DisplaySetMode(&display, &VMODE_1280x720);
    if (status == XST_SUCCESS)
        status = DisplayStart(&display);
    if (status != XST_SUCCESS) {
        xil_printf("HDMI timing initialization failed: %d\r\n", status);
        return XST_FAILURE;
    }

    status = run_vdma_frame_buffer(&pose_vdma, XPAR_AXI_VDMA_POSE_DEVICE_ID,
                                   POSE_WIDTH, POSE_HEIGHT,
                                   POSE_BUFFER_ADDR, 0, 0, ONLY_WRITE);
    if (status != XST_SUCCESS) {
        xil_printf("Pose preprocessing VDMA initialization failed: %d\r\n", status);
        return XST_FAILURE;
    }

    xil_printf("Camera/HDMI frame buffer: 0x%08x\r\n", FRAME_BUFFER_ADDR);
    xil_printf("256x144 preprocessing buffer: 0x%08x\r\n", POSE_BUFFER_ADDR);
    print_dpu_probe();
    xil_printf("LOGIC-BRINGUP PASS: observe live 720p video on HDMI.\r\n");

    while (1)
        sleep(1);
}
