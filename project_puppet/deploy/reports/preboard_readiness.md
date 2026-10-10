# XCZU4EV 最新 V2 模型预上板检查

结论：软件与 FPGA 实现门禁已经通过，JTAG、FSBL、bitstream、DDR、PS-PL 释放和 AXI 探测均已上板通过；当前唯一阻塞是 OV5640 SCCB 返回 `0xFFFF`，摄像头模块没有应答。

## 已核验产物

- 模型：`TinyUpperPoseNetV2`，checkpoint SHA256 `01c852378a963ddec52b457d88bc4af2e03aef57847533afd5213d4a6855eb1c`。
- bitstream：SHA256 `ececd4d32c7f72723f0149330d5ad64318d7f9f5491c63a867e59f751a9632de`。
- XSA：SHA256 `3aaafde0648da5679fd596b3bc3aa1e35f98224929a3fc8fda687a0c3766b3d2`。
- FSBL：SHA256 `096fe9de898c91db4dfb1010e3bcc04a53a08ba854638fb0c2dcfe70eeb561f7`。
- PMUFW：SHA256 `5bcf765079ea0d040e3105fe7e532561ae094f4c3c72dbaeec3e10e52024dfb5`。
- A53 ELF：SHA256 `78d366f5d4c0ed3b01b2e66416db5ba3b4cc266844ac69f4eceeff2fac8d9a8e`，ELF64/AArch64/little-endian。
- Python INT8 与 HLS C-sim：36,864 字节 heatmap 完全一致。
- post-route：WNS `+0.935 ns`、TNS `0`、WHS `+0.010 ns`、THS `0`；DRC 无 Error/Critical Warning。

## 板级约束

- 器件 `xczu4ev-sfvc784-2-i` 与 MPSoC-P4 DFZU4EV 匹配。
- HDMI TMDS P 管脚为 `G3/F2/G1/E1`，审计通过。
- 相机工程源约束已改为用户确认的 ATK-OV5640 单目排列：SCL `D10`、SDA `E10`、D0..7 `B10/B11/C11/C12/A11/D12/A12/A14`、PCLK `A15`、PWDN `B15`、VSYNC `D11`、HREF `E12`、RST `A10`、FLASH `B14`。必须重新生成 bitstream/XSA/ELF 后才可重新上板。
- `program_and_run.bat` 会在触碰 JTAG 前重新生成门禁清单；当前 `ready_for_physical_jtag=True`。

## 当前硬件预检

- FTDI 下载器已被 Windows 识别。
- BOOT_CFG 1/2/3/4 全部 ON（`0000`）后，XCZU4EV、PMU、PL、APU 和 Cortex-A53 #0 枚举正常。
- 下载流程完成，视频 VDMA、姿态 VDMA 与 HLS AXI 控制口可访问；HLS 控制口地址已修正为 BSP 生成的 `0xA0020000`。
- A53 启动断点命中相机 SCCB 失败分支；读取 ID 为 `0xFFFF`，期望 `0x5640`。EMIO 两线空闲高且方向/输出使能正常。
- 用户实际使用商品 `609758211612` 对应的 ATK-OV5640 单目 2x9 模块。它不能直接错位插入 J19；下一次物理操作必须在断电状态下，按 `deploy/reports/atk_ov5640_single_camera_adapter.md` 的信号表通过转接线/转接板连接。模块 `VCC3.3` 只接 J19-3，`GND` 接 J19-2，严禁接 J19-1 的 5 V。
