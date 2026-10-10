# Zynq USB 摄像头迁移（2026-10-10）

## 当前结果

已增加 UVC/V4L2 采集入口，复用原 YOLO Pose9 DPU 模型、FOLLOW 跟踪和 camera-v2 发送协议。原 OV5640/VDMA 入口保留。新程序不启动舵机服务，不改变十路引脚和角度限位。

**当前仍不能宣布 USB 实拍成功。**在实际板子的 COM13 root shell 检查得到：

- Linux `5.15.36-xilinx-v2022.2`，Python 3.9.9，OpenCV 4.5.2；OpenCV 已启用 V4L2。
- 内核 `CONFIG_USB_XHCI_HCD`、`CONFIG_USB_DWC3`、`CONFIG_USB_DWC3_XILINX`、`CONFIG_USB_VIDEO_CLASS`、`CONFIG_VIDEO_V4L2` 均为 `y`。
- `/proc/device-tree/axi/usb0@ff9d0000` 与 `usb1@ff9e0000` 都是 `disabled`，其 DWC3 子节点同样禁用，pinctrl 节点也禁用。
- `/sys/bus/usb/devices` 为空，未出现 `/dev/video*`，还无法读取摄像头的型号、分辨率和格式。
- 当前 DPU 工程导出的 `system.hwh` 也显示 USB0、USB1、USB3_0、USB3_1 均未启用。
- 使用现有 G13 版 `servo10_vision` 镜像，独立 USB HDMI 输出完成 13 帧灰度测试图切换，MM2S 状态 `0x11000`。这是显示通路测试，**不是摄像头画面或人体识别验收**。

因此，仅修改 Python 的 `/dev/video0` 不能让这块板子出图。根据用户补充的官方资料，已继续完成 USB0 的启动修复候选，详见 [USB 启动修复说明](../hardware/usb/README.md)。当前活动 BOOT.BIN、image.ub、uEnv.txt 保持原样，候选尚未启用。

本轮进一步实测：USB0 的内部复位 1059/1061/1063 均为 1，MIO52–63 为 GPIO。Linux 临时设备树加载后，PMU 固件对 USB0 的引脚、时钟和电源域返回 `-13`，驱动未绑定；已撤回临时覆盖并验证原禁用状态恢复。故需要更新 FSBL 的 PS 初始化和 PMU 配置对象，单改设备树仍不够。

候选已在板端构建并回读校验：`32dd1cd32f9675a4c9acaafe330f8e7a7853f1766637a117cf2b57bd536fe55f`。它只替换 FSBL，原 PMUFW、视觉 PL、BL31、DTB 和 U-Boot 的字节保持一致。Windows 与板端各 8 项启动包/预检测试通过，旧 FSBL 被启用工具正确拒绝。**尚未重启试用候选，也尚未取得 USB 摄像头实拍画面。**

## 新软件的行为

- `integrations/follow/board_usb_follow.py` 默认使用 USB。原 `board_follow_with_sender.py` 默认仍为 `vdma`，也可显式加 `--camera usb`。
- 自动选择 USB 视频采集节点；过滤只有 metadata 的节点。没有设备或存在多个采集节点时明确报错，多设备需指定 `--usb-device /dev/videoN` 或 `/dev/v4l/by-id/...`。
- 默认请求 `MJPG / 1280×720 / 30 fps`，启动日志记录驱动实际协商结果。可选 YUYV、其他宽高和帧率，不把请求值冒充实测值。
- 默认旋转 0°、不镜像，不沿用旧 OV5640 的 180°翻转。其他比例图像保留纵横比，加灰边到 1280×720，使模型、显示和发送的关键点使用同一坐标系。
- 采集在独立进程中连续运行，仅保存最新一帧；读帧超时、拔出设备、无新帧或帧过旧会退出，不循环发送上一次人体结果。时间戳是主机取帧完成时间，不是相机曝光时间。
- `--no-send` 可只验证图像/推理，完全不发送控制输入。`--display none` 可独立验证 USB 和 DPU。
- HDMI 模式不再读取旧摄像头或 Pose drain 的 S2MM 错误。它独立配置 VTC 和 MM2S，仅检查显示通道；目前只允许已验证的 G13 `servo10_vision` 镜像运行标记，防止未知 PL 地址映射。
- HDMI 寄存器通过现有的原生 32 位 MMIO 库访问；不写舵机寄存器。退出后恢复原显示寄存器，原摄像头服务不会自动重启。
- 相机方向或视场改变后，仍需真人确认左/右手对应和跟踪范围；旧摄像头的联调结论不能直接当作新摄像头的验收。

## 板端位置与运行方法

部署目录：`/run/media/mmcblk0p2/piying/shadow-usb-camera-20261010`。依赖板子已有 `/opt/shadow/yolo_pose9/runtime`、`follow` 和原 xmodel，不复制、不重训模型。此目录不会替换原开机服务。

以下命令要在 USB 主机初始化完成后执行。当前设备树禁用时，第一步会输出诊断并返回 2。

```sh
cd /run/media/mmcblk0p2/piying/shadow-usb-camera-20261010
python3 tools/usb_camera_probe.py

# 只验证真实采集，不运行 DPU、HDMI 或发送器。
python3 integrations/follow/usb_camera.py --frames 60

# USB + DPU，不显示、不发送控制输入。
sh tools/run_usb_follow.sh --display none --no-send --frames 120

# USB + DPU + HDMI；测试阶段不发送控制输入。
sh tools/run_usb_follow.sh --no-send

# 确认图像方向及人体检测后，才运行发送关键点的模式。
sh tools/run_usb_follow.sh
```

启动器拒绝与 `shadow-yolo-follow.service`、`shadow-video.service` 并行运行。如它们正在运行，先在当前板端会话停止这两个原摄像头服务，再运行新入口。不要对 USB 模式调用旧 `boot_guard.py video`，它会等待原 OV5640 数据。

设备格式以探测结果为准，例如：

```sh
sh tools/run_usb_follow.sh --usb-device /dev/video0 --usb-format YUYV \
  --usb-width 640 --usb-height 480 --usb-fps 30 --usb-rotation 0 --no-send
```

若没有 `G13 servo10_vision` 运行标记，先用 `--display none`。不要为启动摄像头而直接切换 FPGA；切换镜像仍需先关闭舵机独立电源。

## 板级配置的依据与待确认项

已核对本机官方资料盘中的 `MPSoC_P4_2CG_4EV_1V7.pdf` 第 5、25、26 页：USB0 ULPI 使用 MIO52–63；MIO24 为 `HUB_RESET_IO`，MIO25 为 `USB_RESET_N`；USB3320 接 USB Hub，再分到外部接口。

官方 `4_SourceCode/3_Embedded_Linux/vivado_prj/4ev/base_vcu` 的参考 BD 把 USB0 reset 设为 MIO24，实际控制 Hub；USB3320 的 MIO25 复位线由板上拉电路释放。修复候选遵循这一参考配置：USB0 ULPI/MIO52–63、共享 MIO24 复位、USB2 high-speed；保留 MIO25，不启用 USB3 SerDes。用户补充的《MPSoC-P4之嵌入式Linux开发指南 V2.0》第 1102–1104、1112–1114 页已核对，普通 USB 摄像头的具体型号与格式待成功枚举后直接读取。

系统侧配置依据：[AMD DWC3 Xilinx Linux USB driver](https://xilinx-wiki.atlassian.net/wiki/spaces/A/pages/18841729)、[匹配 2022.2 的 Xilinx DWC3 驱动源码](https://github.com/Xilinx/linux-xlnx/blob/xlnx_rebase_v5.15_LTS_2022.2/drivers/usb/dwc3/dwc3-xilinx.c)。

补齐板级 USB 初始化后需要实测：USB 枚举 → 模式查询 → 连续采集 → DPU 人体骨架 → HDMI → camera-v2 输入。最后再在有人可随时断电时做真实机构联调。当前尚未修改为开机自启；应在实际相机和启动配置验证通过后再集成。

## 验证与复现

```sh
# 板端已有 OpenCV 和原 FOLLOW runtime。
PYTHONDONTWRITEBYTECODE=1 python3 tests/test_usb_camera.py
```

测试涵盖 USB capture/metadata 能力区分、多设备拒绝、画面比例和方向、最新帧替换、帧过旧/超时、子进程打开失败和回收、仅检查 HDMI MM2S、USB 到 FOLLOW 发送集成以及启动失败清理。测试中的模拟帧和模拟模型不计作实物摄像头或 DPU 识别结果。

本轮实测：板端 15 项 USB 回归通过；现有关键点发送器 11 项测试通过（包括真实本机 UDP 收发）。Windows 沙盒中的首次回环收包曾超时，允许本机网络后同一测试全部通过。部署包逐文件 SHA-256 与 SD 回读一致；启动器在当前 USB 控制器关闭时正确返回 2，未启动 DPU/显示/发送流程。

宿主机可用 `python shadow_play/tools/package_usb_follow.py <新的.tar.gz路径>` 生成源码包，包内 `SHA256.json` 记录各文件校验值。原始探测和测试日志留在本地 `.review_work/usb_camera_20261010/`，不包含录制画面。
