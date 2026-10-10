# 最新 V2 HLS INT8 实施状态

更新时间：2026-09-19（Asia/Shanghai）

## 已完成

- 根目录 `best.pt` 已严格加载为 `TinyUpperPoseNetV2`；输入 `1×3×144×256`、输出 `1×9×36×64`、完整 state-dict 和固定 14 层顺序校验通过。
- checkpoint SHA256 固定为 `01c852378a963ddec52b457d88bc4af2e03aef57847533afd5213d4a6855eb1c`；未使用已废弃的旧人工复核数据。
- Conv+BN 确定性融合、浮点回退头文件、逐输出通道 INT8 参数、量化元数据与 NPZ 定点参考均已重新生成。
- Python 定点与完整 14 层 Vitis HLS C-sim 的 36,864 字节 heatmap 完全一致，mismatch 为 0。
- 用户提供了 ATK-OV5640 单目模块的完整 16 路管脚约束；已将工程源约束更新为：SCL `D10`、SDA `E10`、D0..7 `B10/B11/C11/C12/A11/D12/A12/A14`、PCLK `A15`、PWDN `B15`、VSYNC `D11`、HREF `E12`、RST `A10`、FLASH `B14`。`cam_flash` 已恢复并固定输出低电平。
- 已重新生成 Vivado 工程、综合、布局布线、bitstream 和含 bitstream 的 XSA。目标器件为 `xczu4ev-sfvc784-2-i`。
- 最终实现完全布通：failed/unrouted/partially-routed nets 和 node overlaps 均为 0；WNS `+0.935 ns`、TNS `0`、WHS `+0.010 ns`、THS `0`，所有用户时序约束满足。
- post-route DRC 无 Error/Critical Warning；435 项均为 DSP 流水线、BRAM 碰撞建议或无可路由负载等 Warning。
- 新 bitstream SHA256 为 `ececd4d32c7f72723f0149330d5ad64318d7f9f5491c63a867e59f751a9632de`；新 XSA SHA256 为 `3aaafde0648da5679fd596b3bc3aa1e35f98224929a3fc8fda687a0c3766b3d2`。
- Vitis 2022.2 已基于新 XSA 重新生成 XCZU4EV 平台、FSBL、PMUFW、standalone BSP 和 A53 应用 ELF。
- ELF SHA256 为 `78d366f5d4c0ed3b01b2e66416db5ba3b4cc266844ac69f4eceeff2fac8d9a8e`；为小端 AArch64 ELF64，装载范围 `0x00000000..0x000D4D3F`，不与 `0x01000000` 起始的视频缓冲区重叠。
- 固件结果结构为 v7、224 字节、小端固定宽度；输入快照 `0x02300000`、INT8 heatmap 快照 `0x02400000`，每 30 帧原子提交。验证构建禁止静默回退 PS。
- 预上板门禁通过：相机和 HDMI 管脚均 0 mismatch，bitstream/XSA 时间关系正确，`ready_for_physical_jtag=True`。

## 当前上板状态

- BOOT_CFG 四位全部 ON 后，XSCT 已完整枚举 PS TAP、PMU、PL、APU 与 Cortex-A53 #0。
- 已通过门禁脚本完成 FSBL、bitstream、PS-PL 隔离/复位释放和 A53 ELF 下载。
- AXI 探测通过：视频 VDMA `0xA0000000`、姿态 VDMA `0xA0010000`、HLS 控制口 `0xA0020000` 均可访问；HLS 控制值 `0x00000004` 为有效空闲状态。
- 无串口断点诊断确认 A53 在 `ov5640_init()` 后进入相机失败分支。两次 SCCB 读取均为 `0xFF`，实际组合 ID 为 `0xFFFF`，期望值为 `0x5640`。
- SCCB 空闲电平与 PS GPIO 状态正常：EMIO Bank 3 `DATA_RO=0x3`、`DIRM=0x3`、`OUTEN=0x3`。因此当前阻塞收敛为摄像头模块未应答，而非 JTAG、DDR、AXI 或 HLS 核不可访问。
- 用户确认实际模块为商品 `609758211612` 对应的 ATK-OV5640 单目 2x9 模块，并补充了完整 FPGA 封装脚约束。原 bitstream 使用了错误的信号排列，因此此前 `0xFFFF` 不能再用于判断模块损坏。
- 已依据用户约束、MPSoC-P4 V1.7 原理图和当前 XDC 更新 `deploy/reports/atk_ov5640_single_camera_adapter.md`：单目信号映射到 J19-4..19，3.3 V/GND 分别取 J19-3/J19-2，J19-1 为 5 V，严禁接入模块电源。

## 待完成

1. 使用用户确认的新管脚约束重新实现 bitstream、导出 XSA、重建 ELF，并更新预上板门禁清单。
2. 保持断电，依据模块 PCB 丝印和 `atk_ov5640_single_camera_adapter.md` 复核单目模块到 J19 的连接；确认模块 3.3 V 没有接到 J19-1 的 5 V，再上电复测芯片 ID `0x5640`。
3. 相机通过后确认 HDMI、双 VDMA 和姿态循环启动，并通过 JTAG 结果快照核验 `backend=PL`、`layers=14`、`failed_layer=0` 和模型哈希。
4. 采集 200 个真实 `256×144 RGB` ROI，替换 provisional 校准参数并重新导出/重编 ELF。
5. 另采集至少 50 个原子快照完成 FPGA heatmap 逐字节一致性验证，并连续运行 10 分钟记录 FPS/时延。

最终结论仍称为“部署一致性验证”；没有人工真值时不输出或宣称真实 PCK。
