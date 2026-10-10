# Zynq USB 摄像头迁移（2026-10-10）

## 当前结果

已增加 UVC/V4L2 采集入口，复用原 YOLO Pose9 DPU 模型、FOLLOW 跟踪和 camera-v2 发送协议。原 OV5640/VDMA 入口保留。新程序不启动舵机服务，不改变十路引脚和角度限位。

**USB 实拍、板端 DPU 推理和 HDMI 输出已通过实测，USB 初始化已通过正常自动重启验证。**

| 项目 | 2026-10-10 实测结果 |
| --- | --- |
| 摄像头 | `icspring camera` / `icSpring`，USB VID:PID `32e6:9211`，UVC 1.00 |
| 视频节点 | `/dev/video0` 是采集节点；`/dev/video1` 是 metadata，不作为图像输入 |
| 实际协商 | MJPG、1280×720、30 fps；实际观察的整条推理/显示流程约 **15 fps**，不能把协商值当作实际帧率 |
| 真实采集 | 连续 60 帧通过；最终 USB 启动配置重启后再测 60 帧通过 |
| DPU | 120 帧无显示实拍推理通过；硬件指纹匹配；单帧 DPU 时间约 14.8 ms |
| HDMI | G13 `servo10_vision` 上 120 帧实拍推理显示通过，随后持续预览；MM2S `0x11000`，日志无显示错误 |
| 重启 | U-Boot 输出 `Piying USB2 and SD disable-wp applied`；Linux 自行枚举相机，不依赖手动 configfs overlay；SD `ro=0` |
| 电机 | 整轮保持独立电源关闭；PWM `armed=false`、`enabled_mask=0`；实际预览使用 `--no-send` |
| 待现场验收 | 当前测试画面日志为 `people=0`。需要用户进入镜头确认骨架、左右对应及方向，不能据此宣布真人跟随或电机联动完成 |

Linux `5.15.36-xilinx-v2022.2` 已内置 UVC、DWC3、xHCI，OpenCV 4.5.2 支持 V4L2。原故障是 FSBL 未初始化/授权 USB0，且设备树禁用控制器。新 BOOT 只更换 FSBL，原 PMUFW、视觉 PL、BL31、DTB、U-Boot 不变；新增 USB 设备树覆盖由 `uEnv.txt` 在启动时加载。原 `image.ub`、`boot.scr` 保留，启动文件有备份，详见 [USB 启动修复说明](../hardware/usb/README.md)。

**持久化范围：摄像头驱动开机可用，程序文件保存在 SD。USB 骨架预览目前由手动入口启动，没有写入原 RAM 根文件系统镜像的自启服务。**当前 `shadow-usb-preview.service` 是本次启动内的临时服务，重启后需按下文重新启动。原 OV5640 服务尚在原镜像里，运行 USB 入口前需停止它们。

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

以下命令在板端 root shell 执行。新启动配置会自动启用 USB；不再重复运行 `enable_p4_usb_host.py --apply`。

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

每次 Zynq 重启会恢复 BOOT 内的原视觉 PL。若没有 `/run/shadow-pwm-loaded.json` 中的 G13 运行标记，可先用 `--display none` 验证 USB/DPU。**使用 HDMI 前先关闭舵机独立电源**，在尚未加载 G13 镜像时执行一次：

```sh
systemctl stop shadow-yolo-follow.service shadow-video.service
cd /run/media/mmcblk0p2/piying/servo-capture-20261008-r4
python3 integrations/calibration/load_pwm_runtime.py \
  --image hardware/servo_pwm/release/servo10_vision.bit.bin \
  --manifest hardware/servo_pwm/release/servo10.manifest.json \
  --servo-power-off-confirmed
```

此参数代表操作者已实际关闭独立电源；不要在未断电时直接照抄。加载器验证镜像、拒绝并行设备映射、核对 PWM 输出关闭；已有运行标记时不要重复加载。加载后切回 USB 软件目录运行 `sh tools/run_usb_follow.sh --no-send`。

当前持续预览的查询/停止命令：

```sh
systemctl status shadow-usb-preview.service --no-pager
journalctl -u shadow-usb-preview.service --no-pager -n 5
systemctl stop shadow-usb-preview.service
```

## 板级配置的依据

已核对本机官方资料盘中的 `MPSoC_P4_2CG_4EV_1V7.pdf` 第 5、25、26 页：USB0 ULPI 使用 MIO52–63；MIO24 为 `HUB_RESET_IO`，MIO25 为 `USB_RESET_N`；USB3320 接 USB Hub，再分到外部接口。

官方 `4_SourceCode/3_Embedded_Linux/vivado_prj/4ev/base_vcu` 的参考 BD 把 USB0 reset 设为 MIO24，实际控制 Hub；USB3320 的 MIO25 复位线由板上拉电路释放。已启用配置遵循这一参考：USB0 ULPI/MIO52–63、共享 MIO24 复位、USB2 high-speed；保留 MIO25，不启用 USB3 SerDes。用户补充的《MPSoC-P4之嵌入式Linux开发指南 V2.0》第 1102–1104、1112–1114 页已核对。相机除 MJPG 720p30 外，还报告 YUYV 720p10、800×600 15 fps、640×480 30 fps 等模式。

系统侧配置依据：[AMD DWC3 Xilinx Linux USB driver](https://xilinx-wiki.atlassian.net/wiki/spaces/A/pages/18841729)、[匹配 2022.2 的 Xilinx DWC3 驱动源码](https://github.com/Xilinx/linux-xlnx/blob/xlnx_rebase_v5.15_LTS_2022.2/drivers/usb/dwc3/dwc3-xilinx.c)。

尚需现场实测真人骨架、camera-v2 到总控的实际人体输入、最终机构跟随。之后再将已确认的 USB 入口集成进正式根文件系统，完成整机自启及断电启动验收；本次仅验证了正常软件重启。

## 验证与复现

```sh
# 板端已有 OpenCV 和原 FOLLOW runtime。
PYTHONDONTWRITEBYTECODE=1 python3 tests/test_usb_camera.py
```

测试涵盖 USB capture/metadata 能力区分、多设备拒绝、画面比例和方向、最新帧替换、帧过旧/超时、子进程打开失败和回收、仅检查 HDMI MM2S、USB 到 FOLLOW 发送集成以及启动失败清理。测试中的模拟帧和模拟模型不计作实物摄像头或 DPU 识别结果。

板端 15 项 USB 回归通过；此前现有关键点发送器 11 项测试通过（包括真实本机 UDP 收发）。新增启动包/FSBL 预检 10 项、启动覆盖安装器 7 项测试通过；安装器的 7 项也在板端通过。Ubuntu 可由源码重新编译出 SHA-256 完全相同的三个覆盖文件。部署文件均做 SHA-256 校验。

宿主机可用 `python shadow_play/tools/package_usb_follow.py <新的.tar.gz路径>` 生成源码包，包内 `SHA256.json` 记录各文件校验值。原始探测和测试日志留在本地 `.review_work/usb_camera_20261010/`，不包含录制画面。
