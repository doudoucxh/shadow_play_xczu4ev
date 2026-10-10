/* Based on ALIENTEK OV5640 examples. Camera RGB565 -> PL RGB888 -> DDR -> HDMI. */
#include "xparameters.h"
#include "xstatus.h"
#include "xil_printf.h"
#include "sleep.h"
#include "display_ctrl_hdmi/display_ctrl_hdmi.h"
#include "vdma_api/vdma_api.h"
#include "emio_sccb_cfg/emio_sccb_cfg.h"
#include "ov5640/ov5640_init.h"
#include "pose_inference.h"

#if defined(XPAR_PSU_DDR_0_S_AXI_BASEADDR)
#define DDR_BASE_ADDR XPAR_PSU_DDR_0_S_AXI_BASEADDR
#elif defined(XPAR_PSU_DDR_0_BASEADDRESS)
#define DDR_BASE_ADDR XPAR_PSU_DDR_0_BASEADDRESS
#else
#define DDR_BASE_ADDR 0x00000000U
#endif

#define FRAME_BUFFER_ADDR (DDR_BASE_ADDR + 0x01000000U)
#define CAMERA_WIDTH 1280U
#define CAMERA_HEIGHT 720U
#define CAMERA_TOTAL_WIDTH 2570U
#define CAMERA_TOTAL_HEIGHT 980U
#define POSE_WIDTH 256U
#define POSE_HEIGHT 144U
#define POSE_BUFFER_ADDR (DDR_BASE_ADDR + 0x02000000U)

static XAxiVdma vdma;
static XAxiVdma pose_vdma;
static DisplayCtrl display;

int main(void)
{
    int status;
    xil_printf("Shadow_play Ultra V3: official P4 720p HDMI path, 16x2 INT8 PL\r\n");
    emio_init();
    status = ov5640_init(CAMERA_WIDTH, CAMERA_HEIGHT,
                         CAMERA_TOTAL_WIDTH, CAMERA_TOTAL_HEIGHT);
    if (status != 0) {
        xil_printf("OV5640 detected failed! Check camera connector, power and SCCB.\r\n");
        return XST_FAILURE;
    }
    xil_printf("OV5640 detected successful!\r\n");

    /* Keep the verified ZYNQ-7020 ordering and start both VDMA directions
     * together so that the capture/display genlock state is established once. */
    status = run_vdma_frame_buffer(&vdma, XPAR_AXIVDMA_0_DEVICE_ID,
                                  CAMERA_WIDTH, CAMERA_HEIGHT,
                                  FRAME_BUFFER_ADDR, 0, 0, BOTH);
    if (status != XST_SUCCESS) {
        xil_printf("VDMA initialization failed: %d\r\n", status);
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
        xil_printf("Pose VDMA initialization failed: %d\r\n", status);
        return XST_FAILURE;
    }
    xil_printf("VDMA and HDMI started. Frame buffer: 0x%08x\r\n", FRAME_BUFFER_ADDR);
    xil_printf("Pose preprocessing started: 256x144 RGB888 at 0x%08x\r\n",
               POSE_BUFFER_ADDR);
    xil_printf("PL streams video continuously; starting ROI tracking and pose overlay.\r\n");
    pose_run_hardware_test(&vdma, &pose_vdma, FRAME_BUFFER_ADDR, POSE_BUFFER_ADDR);
    while (1)
        sleep(1);
}
