# Shadow_play XCZU4EV migration

Target device: `xczu4ev-sfvc784-2-i` (MPSoC-P4/Ultral).

This directory contains the UltraScale+ port of the verified ZYNQ-7020 pose
pipeline. The HDMI and camera path now follows the official ALIENTEK MPSoC-P4
`29_ov5640_hdmi` example: 1280x720 video, 2570x980 OV5640 totals, 75 MHz pixel
clock, and the official `openedv.com:user:DVI_Transmitter:1.0` IP. The pose
branch decimates the complete 1280x720 frame by 5 to the model's unchanged
256x144 input.

## Hardware pipeline

1. OV5640 8-bit DVP RGB565 capture.
2. RGB565-to-RGB888 conversion in PL.
3. AXI4-Stream split to the display VDMA and pose preprocessor.
4. 256x144 pose input VDMA into PS DDR4.
5. INT8 CNN HLS accelerator with 16 output channels and two input channels per
   MAC step.
6. Three independent 64-bit CNN AXI masters into a high-performance PS DDR port.
7. 1280x720 HDMI output through the official P4 DVI transmitter, using four
   UltraScale+ `OSERDESE3` serializers and four differential output buffers.

The PL/CNN AXI clock is kept at the requested 100 MHz. The HLS core was also
synthesized against a 5 ns target and has an estimated Fmax of 273.97 MHz, so
the 100 MHz integration has ample core timing margin.

## Camera pins

| Signal | Package pin |
| --- | --- |
| SCL | D10 |
| SDA | E10 |
| D0 | B10 |
| D1 | B11 |
| D2 | C11 |
| D3 | C12 |
| D4 | A11 |
| D5 | D12 |
| D6 | A12 |
| D7 | A14 |
| PCLK | A15 |
| PWDN | B15 |
| VSYNC | D11 |
| HREF | E12 |
| RST | A10 |
| FLASH | B14 |

SCL and SDA use PS GPIO through EMIO[0:1]. On Zynq UltraScale+, these are GPIO
numbers 78 and 79 in the standalone application. FLASH is held low.

Pin A15 is not a clock-capable input on this package. The camera PCLK therefore
uses the explicit `CLOCK_DEDICATED_ROUTE FALSE` exception and a BUFG. The routed
camera clock path meets timing with 11.452 ns setup slack and 0.043 ns hold
slack. The 100 MHz CNN clock is unaffected and uses its normal dedicated clock
network.

## Main outputs

- Vivado project: `vivado/Shadow_ultra.xpr`
- Rebuild script: `scripts/create_ultra_project.tcl`
- HLS IP archive: `hls/pose_cnn_accel/pose_cnn_accel_16lane.zip`
- HLS synthesis report: `hls/pose_cnn_accel/build/solution1/syn/report/csynth.rpt`
- Vitis application sources: `vitis/ov5640_hdmi/src`
- Extracted official reference: `official_reference/XCZU4EV/29_ov5640_hdmi`
- Official DVI transmitter IP copy: `ip_repo/DVI_TX`
- Bitstream: `build/system_wrapper.bit`
- Hardware platform with the bitstream embedded: `Shadow_ultra.xsa`
- Compiled A53 application:
  `vitis_workspace_2022_2/ov5640_hdmi_ultra/Debug/ov5640_hdmi_ultra.elf`

The HLS C simulation passes all operations. HLS estimates 39 BRAM18K, 193 DSP,
44,506 FF and 67,005 LUT for the accelerator. All requested HLS loop pipeline
constraints are satisfied after separating the residual reads from the input
AXI port.

The complete routed design contains 292 DSP48E2 (40.11%), 39,300 CLB LUTs
(44.74%), 49,223 CLB registers (28.02%), and 30 block-RAM tiles (23.44%). It has
no failed, unrouted, partially routed, or overlapping nets. Timing signoff
passes with WNS 0.641 ns, TNS 0, WHS 0.010 ns, and THS 0. The remaining
DSP pipeline DRC messages are advisory; there are no DRC errors and bitstream
generation completes successfully.

## Rebuild

Run these from the `Shadow_play` directory in a Vivado/Vitis 2022.2 setup:

```powershell
& 'D:\xilinx\Vitis_HLS\2022.2\bin\vitis_hls.bat' -f ultral_xczu4ev/hls/pose_cnn_accel/run_hls.tcl
& 'D:\xilinx\Vivado\2022.2\bin\vivado.bat' -mode batch -source ultral_xczu4ev/scripts/create_ultra_project.tcl
& 'D:\xilinx\Vivado\2022.2\bin\vivado.bat' -mode batch -source ultral_xczu4ev/scripts/build_ultra_in_process.tcl
& '.\ultral_xczu4ev\build_firmware.bat'
```

Programming is intentionally left to the board owner. The build
script packages `build/system_wrapper.bit` into `Shadow_ultra.xsa`
automatically; `scripts/package_xsa_with_bitstream.ps1` can also repeat that
packaging step without rerunning implementation.

Before JTAG, run `scripts/package_preboard.ps1`. `program_and_run.bat` repeats
this check and refuses programming unless `ready_for_physical_jtag` is true.
For the MPSoC-P4 DFZU4EV material currently in this workspace, the HDMI pins
match but the existing camera XDC does not match either official connector;
select the intended connector, correct the XDC, and rebuild the bitstream/XSA.

For a JTAG test, set all four boot switches to ON and run the guarded launcher.
It programs the bitstream, runs the FSBL, downloads the application to
Cortex-A53 #0, and starts it:

```powershell
& '.\ultral_xczu4ev\program_and_run.bat'
```

The application's messages are sent to PS UART0 on MIO42/43. Open the board's
`USB_UART (PS_PORT)` as a 115200-8-N-1 Serial Terminal; the TCF Debug Virtual
Terminal is not connected to this stdout device. A successful new download
starts with `Shadow_play Ultra V3: official P4 720p HDMI path, 16x2 INT8 PL`.
