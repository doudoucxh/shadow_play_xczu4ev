# 武松打虎皮影总控软件 · v0.3

**2026-10-30 第二部分动作位置库：**新增根目录 `画画动作库上位机.cmd`，按现有20个武松画画动作及老虎站立逐项读取保存反馈舵机位置，支持手摆、单轴/多轴设角、已存姿势调用、来源区分和版本备份。默认离线，使用当前双总线服务。详见[动作位置库使用说明](docs/bus_servo_pose_library.md)。本次电脑端完成，未部署板端画画识别自动调用，未进行实物动作验收。

**2026-10-27 ID10限时刹车结果：**用户进一步明确请求后，完成一次30秒连续刹车窗口：1415帧排入、无应答，已自动退出。用户上电见转动后迅速断电，随后怀疑是上电回中或反向安装，尚未确认；上电时刻未与窗口独立对时，不能认定刹车已送达。当前保持断电，不自动重试。详见[反馈记录最新续节](docs/bus_servo_feedback_20261027.md#用户进一步明确连续发送一次30秒刹车窗口已结束)。

**2026-10-27 实物检查暂停：**用户确认电气兼容测试完成，四口配置已同步、服务设为只读。但随后上电时ID10疑似持续转动，用户已迅速断电；原定反馈查询在发送前取消。现在保持舵机断电，使用四口入口的离线模拟。详见[电气确认与异常记录](docs/bus_servo_feedback_20261027.md)。

**2026-10-27 四口程序已部署：**BT04包已安装到SD独立目录，FPGA已加载，四路空闲、无故障。映射仍为ID7～10分别接原1～4口，人物暂不连接。此次是当前通电会话的加载，重启仍恢复原PWM镜像；三个实机就绪字段保持false，未发舵机/丝杆报文。详见[部署与重启说明](docs/bus_servo_tiger_deployment_20261027.md)。

**2026-10-26 老虎临时四口：**新增根目录 `老虎四舵机临时调试.cmd`，仅显示老虎7～10号，分别使用原1～4号口 D14/D15/F13/G13；四根信号线相互独立，人物暂不连接。保留角度控制、录制回放和分步剪辑，原十轴双总线入口继续保留。需要独立BT04 FPGA候选，不能只改上位机后直接使用旧PWM镜像。详见[临时接线与运行说明](docs/bus_servo_tiger_four_20261026.md)。本轮仅本地修改，尚未部署或操作实物。

**2026-10-24 分步录入/剪辑：**上位机新增独立编辑窗口，支持逐个读取姿势、移动/停留时间、重新录入、裁剪/分割/删除区间、复制排序、拼接、局部变速、撤销重做及自动草稿。详见[新增操作流程](docs/bus_servo_teaching_20261024.md#分步录入与剪辑新增)，可先打开[模拟练习工程](examples/bus_servo_editing/simulation.project.json)。编辑仅生成动作数据；应用到主窗口后仍需首帧准备再回放。

**2026-10-24 双总线示教：**新增[总线舵机上位机与换装说明](docs/bus_servo_teaching_20261024.md)。人物六路使用原9号E14，老虎四路使用原10号E15；支持单轴/多轴角度、实际反馈录制、手动示教和变速回放。双击根目录 `总线舵机示教上位机.cmd` 可先离线模拟。15kg版本尚未换装，信号电平、实物ID及机械行程待验证；新程序与FPGA候选尚未部署，不能直接沿用原PWM工具和旧姿态。

**2026-10-11 动作准备：**新增 [36 秒武打动作草稿](docs/fight36_rehearsal_20261011.md) 和可选缓起缓停插值，已通过 Ubuntu 离线验证；[五个杆端静态坐标](docs/point_coordinates_20261011.md) 已记录。带杆运动标定尚未完成，动作草稿不能直接驱动实机。

**2026-10-10 USB 摄像头适配：**新增独立 UVC/V4L2 输入、原 Pose9/FOLLOW 复用和 HDMI 输出。应用适配与板端回归已验证；当前系统 USB 控制器被禁用，尚未取得 USB 实拍帧。运行方式与板级待办见 [USB 摄像头迁移说明](docs/usb_camera_migration.md)。

**2026-10-08 舵机采集入口：**本次实物为五组云台、十个舵机，9/10 号控制老虎脚，滑轨固定。Ubuntu 已编译双相机采集界面并通过 19 项测试；十路 PWM 和 PS 串口驱动已新增，实物初始化仍需确认起始参考和机械范围。请优先阅读 [本机十舵机采集说明](docs/servo_capture_20261008.md)。下文 v0.3 总控的模拟电机后端与本次独立采集驱动是不同程序，不能直接混用配置。

**2026-10-03 进展：**用户的 VMware Ubuntu 20.04 已通过 9/9 项测试；ARM64 总控已在实物 Zynq 的 PetaLinux 2022.2 上通过 17 步软件检查。SD 写保护配置已修正，运行包和日志保存到 SD 并通过软件重启验证；新增总控启动、停止、状态查看入口及 90 帧实时模拟输入验证。原视觉可自启，总控仍需手动启动。真人测试按用户要求暂缓，此前的摄像头 DMA 故障仍待稳定性验收。当前结果与操作入口见 [板端联调记录](docs/board_integration.md) 和 [VMware 无板检查](docs/vmware_pc_check.md)。下文部分 WSL/VirtualBox 路径属于早期示例，不能直接套到当前 VMware 或板端。

现在可以在电脑上完整运行：剧本/触控/人体关键点 → 五根杆目标 → 映射、限位、平滑 → 模拟电机输出。总控、映射、音频测试、轨迹图和模拟发送工具使用 C++17；接入队友现有 Python FOLLOW 程序的薄适配层使用 Python 3 标准库。

**当前电机后端导出 CSV 或整组 JSONL，不操作真实电机。**武松连接在脖子处、左手、右手；老虎连接在头部耳朵处、尾巴处。五个云台实际轴数尚未确认，十轴配置只是示例；90 秒文件是用于软件联调的排练数据，正式剧本、配音与机械标定需要你们制作。项目根目录此前的 XC7Z020 摄像头示例没有被改动。

这次视觉交接使用 `FOLLOW` 最终九点结果，经 [Python 适配层](integrations/follow/pose_sender.py) 转成 camera v2 消息。视觉没有单独的脖子点，C++ 用双肩中点近似颈部位置；不再用骨盆带动这根主杆。先看 [视觉到电机的接线与运行说明](docs/vision_to_motor.md)、[输入协议](docs/input_protocol.md) 和 [硬件电机接口](docs/hardware_motor_protocol.md)。发送器已在板端运行，真实正例和摄像头稳定性仍需完成验证。

## 先用你电脑上的 Ubuntu 跑起来

先确认 Ubuntu 运行在哪里：**VirtualBox 虚拟机与 WSL 是两个独立环境**，安装的软件和工程路径不会自动互通。本次成功编译的是 WSL 环境，尚未在你的 VirtualBox Ubuntu 中验证。

**如果终端显示 `peter@peter-VirtualBox`，请先按 [VirtualBox 安装与运行步骤](docs/virtualbox_setup.md) 操作。** `/mnt/d/ZYNQ` 是这里 WSL 的 Windows D 盘路径，不能直接套用到 VirtualBox。

使用 WSL 时，打开 WSL 的 Ubuntu 终端，执行：

```bash
cd /mnt/d/ZYNQ/shadow_play
cmake -S . -B build-linux -G Ninja -DCMAKE_BUILD_TYPE=Debug
cmake --build build-linux --parallel 4
cd build-linux
ctest --output-on-failure
cd ..
```

新 Ubuntu 环境需要先安装依赖，`ctest` 随 `cmake` 一起安装：

```bash
sudo apt update
sudo apt install build-essential cmake ninja-build pkg-config libasound2-dev
```

Windows 原来的 `build` 是上一版原生编译目录；Linux 使用 `build-linux`，两套构建目录不要混用。VS Code 可从 Windows 打开这个文件夹编辑，构建和运行命令在 Ubuntu 内执行。

每一步成功后再执行下一步；编译失败时，可执行文件还没有生成，继续运行演示命令会产生后续的“没有那个文件或目录”。

### 1. 快速检查整场 90 秒

```bash
./build-linux/shadow_show --seconds 92 > build-linux/my_rehearsal.csv
./build-linux/trace_preview build-linux/my_rehearsal.csv build-linux/my_rehearsal.svg
```

这是加速模拟，通常几秒内完成，不会真的等 92 秒，也不会出声。前 90 秒播放剧本，余下 2 秒观察结束后回中。在 Windows 文件管理器打开 `D:\ZYNQ\shadow_play\build-linux\my_rehearsal.svg` 即可看每轴角度曲线。

`trace_preview`、`--output` 和录制选项都拒绝覆盖已有文件；重复操作时给输出换个名字，或者自行删除确认不再需要的生成文件。上面的 shell 重定向 `>` 会覆盖你指定的 CSV。

已经生成的演示结果：

- `output/rehearsal90.svg`：90 秒排练轨迹。
- `output/three_modes.svg`：自动剧目、暂停、触控、体感、停止的组合轨迹。

这些已有图是历史生成物，可能仍标 `wusong_body`/旧轴名；它们不代表当前颈部映射。使用新配置重新运行上面的命令，得到本版轨迹。

### 2. 分别测试触控、体感输入

```bash
./build-linux/shadow_show --mode touch --seconds 4 --replay assets/touch_demo.jsonl > build-linux/touch.csv
./build-linux/shadow_show --mode camera --seconds 4 --replay assets/camera_demo.jsonl > build-linux/camera.csv
```

两份示例都是 0～3 秒的关键点数据。触控使用 v1，摄像头使用带会话和跟踪信息的 v2；摄像头示例包含关键点置信度降低、缺失及恢复。最后一秒不再发送新数据，用于检查超时回中。你仍然不需要真实摄像头、触控屏或电机。

### 3. 测试三模式切换、暂停和继续

```bash
./build-linux/shadow_show --seconds 12 \
  --commands assets/mode_session.csv \
  --replay-at 3500 assets/touch_demo.jsonl \
  --replay-at 7000 assets/camera_demo.jsonl \
  > build-linux/modes.csv
```

过程：0 秒自动剧目，1 秒暂停，2 秒继续，3.5 秒触控，7 秒体感，11 秒停止。暂停时冻结最后输出的电机指令；停止时按限速回中。这里只是 12 秒的软件测试，90 秒正式排练没有被缩短。

### 4. 用两个 Ubuntu 终端模拟与队员二实时通信

终端 A：

```bash
cd /mnt/d/ZYNQ/shadow_play
./build-linux/shadow_show --mode touch --seconds 60 --realtime \
  --listen 56000 --control-port 56001 \
  --record-input build-linux/live_frames.jsonl \
  --record-commands build-linux/live_commands.csv \
  > build-linux/live_trace.csv
```

终端 B（等待终端 A 显示两个 UDP 端口就绪）：

```bash
cd /mnt/d/ZYNQ/shadow_play
./build-linux/shadow_send --port 56000 --file assets/touch_demo.jsonl
./build-linux/shadow_send --port 56001 --command camera
./build-linux/shadow_send --port 56000 --file assets/camera_demo.jsonl
```

也可以运行交互控制台，逐行输入命令：

```bash
./build-linux/shadow_send --port 56001 --console
```

命令有 `script`、`touch`、`camera`、`pause`、`resume`、`restart`、`stop`、`reset-inputs`、`quit`。暂停/继续只用于自动剧目。接收端会打印是否接受命令；UDP 发送成功不等于业务命令已被接受。

**两个终端都要在同一个 Ubuntu 环境里运行。**此初版固定使用 `127.0.0.1`，适合最终板上各进程通信，未设置跨电脑网络入口。一个 UDP 数据报是一整帧 JSON，最多 16 KiB。收到控制命令时会清掉等待中的旧坐标，接下来由发送方持续发新帧。

同一来源的 `seq` 必须持续递增。重复发送从 seq=0 开始的同一示例会被当成旧数据；重启模拟发送者前，先依次发送 `stop`、`reset-inputs`、`touch`（或 `camera`），再发数据。

camera v2 会固定当前会话：视觉重启导致 `session_id` 改变，或者同来源协议版本改变，会锁定输入并要求 `stop → reset-inputs → camera`。当前摄像头模式中跟踪人物改变会停止并回中；确认画面中的受控人物后发送 `camera` 重新进入模式，接收后续新帧。详见输入协议的状态处理说明。

### 5. 录下来再回放

终端 A 的记录会同时保存有效输入帧和已接受的控制命令，之后运行：

```bash
./build-linux/shadow_show --seconds 60 \
  --replay build-linux/live_frames.jsonl \
  --commands build-linux/live_commands.csv \
  > build-linux/replayed_trace.csv
```

记录采用接收端本地时间。离线固定周期录制/回放已验证角度轨迹逐字一致；真实实时运行存在 Linux 调度抖动，重新回放用于重现输入和控制顺序，不保证每个浮点输出逐字一致。非法 JSON 不录入，重复或非当前来源的有效帧会保留，便于检查序号和模式行为。

### 6. 准备和测试音频

默认 `--audio clock` 是静音模拟时钟。可以生成一份每秒轻响一次、仅用于对时的 90 秒 WAV：

```bash
./build-linux/make_cue_wav build-linux/cue90.wav 90
```

在具有可用 Linux 音频设备的环境里，用真实播放时间驱动动作：

```bash
./build-linux/shadow_show --realtime --seconds 92 \
  --audio device --wav build-linux/cue90.wav \
  > build-linux/audio_trace.csv
```

音频后端使用 ALSA，要求 PCM16 单声道/双声道 WAV。WAV 和剧本时长须相差不超过 1 ms；文件格式错误、声卡打不开、欠载或设备不支持暂停都会明确报错。设备可用 `--audio-device NAME` 选择。WSL 能编译 ALSA 不代表默认声卡已可播放；最终板上的声卡/驱动仍要单独验证。

当前没有你们最终的旁白、配乐和打斗音效。生成的 cue WAV 是测试声音。最终音频也可在剧本根字段 `audio_file` 指定，路径相对于剧本文件所在目录。

## 程序结构

```text
script.json ----------> Script::sample(audio_position) --+
触控 JSON -> 解析 -----> Retargeter ----------------------+-> ShadowPose
人体 JSON -> 解析 -----> Retargeter ----------------------+       |
                                                              MotionMapper
                                                                  |
                                                        每轴 angle_deg
                                                                  |
                                              MotorBackend（CSV / JSONL 导出）
```

| 模块 | 文件 | 当前完成的行为 |
| --- | --- | --- |
| 总控和模式管理 | `controller.hpp/.cpp`、`show_main.cpp` | 三模式、暂停恢复、重播、停止、来源选择、输入序号/会话/换人检查 |
| 剧本 | `script.hpp/.cpp` | 严格检查 JSON、五根杆完整性、时间顺序、关键帧插值 |
| 音频 | `audio.hpp/.cpp` | 静音模拟时钟、WAV 检查、可选 ALSA 播放、按已播放采样同步 |
| 输入与重定向 | `input.hpp/.cpp` | v1/v2 JSON、置信度、镜像、肩宽归一化、双肩中点近似颈部 |
| 共用映射 | `motion_mapper.hpp/.cpp` | 每轴线性标定、角度限制、平滑、限速、逐杆超时 |
| 通信 | `udp.hpp/.cpp`、`input_sender.cpp` | 本机非阻塞 UDP，模拟发送与控制台 |
| FOLLOW 适配 | `integrations/follow/pose_sender.py` | 九点像素转归一化坐标、过滤无效点、会话/跟踪信息、本机 UDP |
| 录制/配置 | `runtime_io.hpp/.cpp` | 输入与命令记录、定时控制命令、参数加载 |
| 电机适配 | `motor_backend.hpp/.cpp` | 可替换后端接口；默认 CSV，`--motor-format jsonl` 导出整组最终角度 |
| 轨迹查看 | `trace_preview.cpp` | 各轴目标/输出 SVG 曲线和状态标记 |
| 音频对时工具 | `make_cue_wav.cpp` | C++ 生成测试 PCM WAV |

## 你接下来按这个顺序做

1. 跑上面的三个离线场景，打开两份 SVG，理解目标值和限速后输出的区别。
2. 把 `docs/vision_to_motor.md`、`docs/input_protocol.md`、`integrations/follow/pose_sender.py` 和两个输入示例交给队员二。让他在最终 `pose` 产生后调用适配层，确认实际左右、模式/重启控制和丢人数据；触控继续按 v1 发送。先本机模拟，再接真实 FOLLOW。
3. 把 `docs/team_handoff.md` 里的电机表交给队员一，确认真实轴数、方向、归位、限位和后端接口。硬件队友实现真实 `MotorBackend`，你根据实测表更新应用标定配置。
4. 你负责把 `assets/storyboard.csv` 和 `assets/rehearsal90.json` 改成真正的 90 秒分镜/动作；准备最终 WAV。先在电脑上用时间轴和曲线检查，再上机构调动作。
5. 你把完整 C++ 源码、CMake/依赖、FOLLOW Python 适配层、配置、剧本、音频和电脑测试说明交给硬件队友。由他使用匹配的 PetaLinux SDK 交叉编译、接入硬件后端和外设驱动、部署 SD 卡，再共同联调。普通 Ubuntu 编译成功不代表目标 ARM64 二进制或整张 SD 卡已完成。

细节文档：

- `docs/project_workflow.md`：三人详细分工、三个任务的 PS/PL/AXI 数据流，以及开发、部署和上电全过程。
- `docs/input_protocol.md`：队员二的输入协议和重定向约定。
- `docs/vision_to_motor.md`：从 FOLLOW 九点输入到电机目标的具体接入步骤。
- `docs/hardware_motor_protocol.md`：交给硬件队友的 C++ 后端与 JSONL 整组电机目标格式。
- `docs/team_handoff.md`：三个人各自交付哪些文件和接口。
- `docs/mapping.md`：映射核心、标定和超时机制。
- `docs/preview.md`：怎样读轨迹图。
- `docs/validation.md`：实际测试结果及未验证部分。

## 给 PetaLinux 集成人员

JSON 解析库已固定版本放在 `third_party`，构建不需要联网。最低 C++17/CMake 3.16；Linux 实际音频需要目标系统的 ALSA 库。可用 `-DSHADOW_REQUIRE_ALSA=ON` 要求配置阶段必须找到音频库；只做静音模拟可关闭 `SHADOW_ENABLE_ALSA`。

使用目标 SDK 的环境脚本、编译器和 CMake 工具链新建 `build-arm`，不要复用 `build-linux` 的缓存；这些路径要等你们实际 SDK 确认。项目可在 PetaLinux 的 CMake 应用 recipe 中构建。`cmake --install` 安装四个工具到 `bin`，示例 `assets` 和 `config` 到 `share/shadow-play`。安装后应明确指定配置和资源的路径，CLI 默认的相对路径用于源码目录演练。

当前真实驱动/寄存器接口尚未确定，所以可执行程序始终使用模拟电机后端；不能仅把本程序拷进 SD 卡就当成已经接好了电机。
