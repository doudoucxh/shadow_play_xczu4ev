# ATK-OV5640 单目模块与 MPSoC-P4 J19 连接说明

更新时间：2026-09-19（Asia/Shanghai）

## 结论

用户提供的商品 `609758211612` 是 ATK-OV5640 单目摄像头模块，外部接口为 2x9、2.54 mm 排针。MPSoC-P4 官方摄像头扩展口 `J19` 是 2x20，官方开发指南面向 ATK-Dual-OV5640 双目模块。

两者信号电平与 DVP/SCCB 协议兼容，但机械针序不相同。单目模块不能按“D11/D10 那一组”直接错位插入 J19；应使用按信号名逐线连接的转接线或转接板。接线和拔插必须在开发板断电状态下进行。

ATK-OV5640 单目模块自带 24 MHz 有源晶振和所需 LDO，因此当前 FPGA 设计不需要输出 XCLK；供电只能接 3.3 V，不能接 J19-1 的 5 V。

## 用户确认的单目摄像头约束

下表由 MPSoC-P4 V1.7 原理图第 4、30 页和 `camera_dvp.xdc` 交叉核对得到。模块端必须按板上丝印信号名连接，不应只按模块排针的相对位置猜测。

| 单目模块信号 | J19 物理针号 | FPGA 封装脚 | 当前顶层端口 |
|---|---:|---|---|
| GND | 2 | - | GND |
| VCC3.3 | 3 | - | 3.3 V |
| OV_SCL | 4 | D10 | `cam_scl` |
| OV_VSYNC | 5 | D11 | `cam_vsync` |
| OV_SDA | 6 | E10 | `cam_sda` |
| OV_HREF | 7 | E12 | `cam_href` |
| OV_D0 | 8 | B10 | `cam_data[0]` |
| OV_RESET | 9 | A10 | `cam_rst_n` |
| OV_D2 | 10 | C11 | `cam_data[2]` |
| OV_D1 | 11 | B11 | `cam_data[1]` |
| OV_D4 | 12 | A11 | `cam_data[4]` |
| OV_D3 | 13 | C12 | `cam_data[3]` |
| OV_D6 | 14 | A12 | `cam_data[6]` |
| OV_D5 | 15 | D12 | `cam_data[5]` |
| OV_PCLK | 16 | A15 | `cam_pclk` |
| OV_D7 | 17 | A14 | `cam_data[7]` |
| OV_PWDN | 18 | B15 | `cam_pwdn` |
| OV_FLASH/STROBE | 19 | B14 | `cam_flash`，固定输出低电平 |

## 上电前门禁

1. 开发板断电，USB/JTAG 和主电源均停止给板卡供电。
2. 以模块 PCB 丝印为准确认 `VCC3.3`、`GND`、`OV_SCL`、`OV_SDA`、`OV_D0..7`、`OV_PCLK`、`OV_PWDN`、`OV_VSYNC`、`OV_HREF`、`OV_RESET`；不要根据镜头朝向推断排针编号。
3. 用万用表通断档复核模块 3.3 V、GND 与 J19-3、J19-2，确认它们没有接到 J19-1（5 V）。
4. 复核其余信号后再上电。当前 FPGA 将 `OV_FLASH/STROBE` 固定输出低电平。
5. 上电后先只运行 SCCB ID 诊断；读到 `0x5640` 后才继续启动 HDMI、VDMA 和姿态推理。

## 当前诊断证据

- JTAG、FSBL、bitstream、DDR、PS-PL 复位释放和三个 AXI-Lite 控制口均已通过。
- A53 在 `ov5640_init()` 的 ID 检查处失败，读回 `0xFFFF`，期望 `0x5640`。
- SCCB 两线在 PS GPIO 侧空闲高且方向/输出使能正确。

因此当前故障与模型、HLS 核或 AXI 地址无关，优先级最高的是修正摄像头物理连接。
