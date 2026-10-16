# 板端接入版 r3：实现与未完成项

基于用户提供的 `shadow-theatre-hdmi-1024x600-20261016-r2.zip`。
原包 SHA256：`8659bd824a4abf9b672c126a551c56cb3e884a9ec9151c70e1886d230d6e634f`。

## 当前交付状态

已实现真实数据接线代码，**尚未安装到板子、尚未验收 HDMI、相机或电机实控**。
2026-10-16 本机未发现板端 COM3；当前枚举到的串口均为蓝牙虚拟串口。
原包模型与素材保留；历史 DESKTOP_QA/MODEL_QA 报告是原包证据，不是本次板端验收。

| 功能 | 接入情况 |
| --- | --- |
| 页面、字体、手绘识别 | 原 r2 UI，增加实际服务状态、请求失败提示 |
| 相机 / 人体识别 | 复用 USB → Pose9 DPU → FOLLOW；同一真实帧生成 JPEG 与关键点，经板端 HTTP 给 UI |
| 角色拖动 / 丝杆滑条 | 仅在松手 / 确认时提交实控意图；缺少实际丝杆驱动和回零、行程、限位资料，目前明确拒绝实控 |
| 人体驱动皮影 | 没有核准的人体坐标到三杆逆解；不使用示例比例或旧指令冒充标定，当前拒绝运动 |
| 经典表演 | 屏幕预览与实机请求分开；没有将历史一次性剧本路线接成可反复调用按钮 |
| HDMI / 触摸 | 保留原启动器的图形环境检查；HTTP 正常不代表 PL HDMI 已显示网页 |

## 运行布局与依赖

完整发布包保留 `shadow_play/hdmi_ui`、`shadow_play/integrations/follow`、`shadow_play/tools` 相对位置。
板子需要原有 `/opt/shadow/yolo_pose9/runtime`、`follow`、Pose9 xmodel、VART/XIR、OpenCV 和 NumPy。
相机识别进程和 UI 服务须使用同一个有设备权限的用户；不通过网页提升权限。
新服务只监听 `127.0.0.1`，没有开启局域网视频访问、远程运动端口或新增账户权限。

在具备 ARM64 浏览器、已接到 HDMI 的图形会话中，以该图形用户运行：

```sh
sh shadow_play/hdmi_ui/runtime/check-board.sh
sh shadow_play/hdmi_ui/runtime/start-linux.sh
```

若只检查 API，可独立运行 `python3 shadow_play/hdmi_ui/runtime/serve.py`。
这条命令只启动 HTTP；相机需在“以身入戏”点“开启姿态识别”才启动。
启动器不会改 FPGA、SD 启动镜像、显示寄存器、系统自动登录或原服务。
如果现有视觉服务正在占用相机，新进程会拒绝启动，不擅自结束它。

UI 仍要求图形输出链路。原 USB HDMI 是 1280×720 VDMA，不是浏览器桌面。
若实板没有相应图形栈，必须先核对当前系统再选择图形镜像或真正的渲染/触摸桥；本版没有实现该显示桥。

## 实拍传输和生命周期

服务显式启动 `run_usb_follow.sh --display none --no-send --ui-feed-file /tmp/.../latest.json`。
该组合禁止 UDP 控制输入和 HDMI 输出，避免抢屏或将识别结果送入电机链路。
FOLLOW 独占相机；浏览器不再同时 `getUserMedia` 抢占 USB。

发布器最高 10 Hz，同一次采集的图像和最终跟踪关键点一起原子替换一个临时 JSON。
图像缩小为 640×360 JPEG；坐标来自同一正向 1280×720 帧，归一化后仍一致。
USB 默认不旋转，不额外沿用旧 OV5640 的 180°翻转。
无检测时 pose 为空；低置信度点省略；不补造遮挡点。相机帧不进入 Git 或动作库。
服务拒绝早于本次启动、未来时间、超过 750 ms、会话变化或序号回退的数据。
UI 还检查传输耗时、JPEG 解码和尺寸，过期或断线清空画面和旧骨架。
退出模式、隐藏页面或停止识别会请求关闭本服务启动的进程；客户端消失超过 10 秒也会回收。

## 控制 API 的实际边界

`GET /api/status` 返回服务、相机和能力状态；服务连接不能等同于实际板子连接。
`POST /api/camera/start`、`POST /api/camera/stop` 管理本服务自己的识别进程。
`GET /api/camera/frame` 返回新鲜的同帧实拍与姿态。
`POST /api/control` 接受界面意图，**当前所有运动请求都返回 409 和明确原因**。
不存在解锁、任意 PWM、回中或执行 shell 的网络入口。
POST 校验同源 Origin、Host 和本次服务随机 token；没有 CORS 放行。

现有 C++ motor backend 只有 CSV/JSONL 导出，56000/56001 是输入/模式端口，不是物理丝杆驱动。
现有 `CaptureDriver` 明确拒绝可控 slides；不能用其舵机 PWM 假装控制丝杆。
后续需要实际丝杆驱动接口、接线、零点、限位、速度/加速度和可用行程，以及当前起点和多杆映射核验。
实控适配还需要单一所有者、已采用指令确认、序号和失联停止机制，不能仅将 ready 改为 true。
动作锁与禁用路线保留，S/T 的历史记录不构成任意实时跟随授权。

## 本地验证

```sh
python -m unittest discover -s shadow_play/tests -p test_hdmi_board_service.py -v
python -m unittest discover -s shadow_play/tests -p test_ui_frame_feed.py -v
node --test shadow_play/hdmi_ui/tests/board-client.test.cjs
python shadow_play/hdmi_ui/tools/build_ui.py
python shadow_play/hdmi_ui/tools/verify_integrity.py
python shadow_play/tools/package_hdmi_board.py shadow_play/build-hdmi-board/shadow-theatre-board-20261016-r3.tar.gz
```

这些是离线/本机测试，测试相机替身和合成图不能当作真实板端效果。
