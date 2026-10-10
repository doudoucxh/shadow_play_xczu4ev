# Zynq皮影总控与整机联调工作手册

适用分工：总控软件与整机联调　　整理日期：2026年9月23日

## 1 当前系统状态与你的工作目标

**这块板已经有 Linux 系统和视觉运行环境。你接下来应在现有系统上完成总控部署与联调，不必先从零重装系统。** 最新视觉交接记录明确出现了 Linux 终端、systemd 服务、Python、OpenCV、XIR、VART、/dev/dpu 和模型安装路径。实际板卡为正点原子 MPSoC-P4，器件 XCZU4EV；早期 Zynq-7020、V2 HLS 裸机文档属于其他阶段。

| 层次 | 交接记录中的状态 | 对你的影响 |
| --- | --- | --- |
| Linux 与基础视频 | 已有可冷启动的纯视频 SD 基线 | 保留作为恢复基线 |
| DPU 与模型 | 板上已有 B4096 DPU、模型和基础运行库 | 复用匹配的环境，不自行更换模型 |
| 最新 FOLLOW | 已有上板运行记录，入口在 /tmp，服务为临时服务 | 重启后通常需要重新传文件、启动 |
| C++ 总控 v0.3 | WSL 中 9/9 项测试通过的历史记录 | 你需要在自己的环境复现 |
| 视觉到总控 | 发送器及集成入口源码已提供 | 需要真实板端联调 |
| 电机与整机 | 当前后端仅输出 CSV 或 JSONL | 真实驱动、标定和系统集成仍待完成 |

最新 FOLLOW 尚未永久安装或开机自启动。“Linux 能启动”“骨架能显示”“电机能跟随”“开机即可演出”是四个不同的完成节点。当前资料不能证明后两项已经完成，也不能证明开发板此刻正在运行哪一个服务。

你的最终交付是：可在目标板运行的总控程序、已确认的视觉和电机接口、实物标定参数、正式剧本及音频、联调记录，以及经过冷启动验证的运行流程。底层驱动由硬件队友实现，你负责接口衔接和整体效果验收。

**执行顺序：确认基线 → 电脑模拟 → 本机 UDP → 板端真实视觉但只导出角度 → 单轴与多杆标定 → 正式演出 → 自启动与定版。** 先完成上一阶段的验收，再接入下一层。

<!-- PAGEBREAK -->

## 2 接手时先确认什么

本机文件根目录为 `D:\Desktop\piying`。最新视觉以 `handoff_visual_follow_20260922/交接说明.md` 为准；总控以 `shadow_play/docs/vision_to_motor.md` 为准。`project_puppet` 保留了多个历史方案，不按某个旧 README 的“当前版本”直接更换已验证系统。

**你先向两位队友取得以下资料，集中记录到一个交接表。**

| 提供人 | 必须确认的内容 | 需要拿到的结果 |
| --- | --- | --- |
| 视觉队友 | 当前入口、运行目录、服务名、近期改动、左右语义 | 可恢复的 FOLLOW 文件和一份真实输入记录 |
| 硬件队友 | 当前 SD 镜像、Linux 信息、启动流程、SDK | 可恢复启动包及匹配的 ARM64 构建方法 |
| 硬件队友 | 实际电机轴数、通道、归位、限位、驱动接口 | 真实轴表和电机后端交付计划 |
| 三人共同 | 现场演示模式、正式时长、分镜、操作员行为 | 一份一致的演示验收清单 |

在开发板已登录的 Linux 终端执行以下只读检查，并保存终端输出。不要在 Windows PowerShell 或电脑 Ubuntu 中把这些结果当成板端结果。

```bash
uname -a
uname -m
cat /etc/os-release
ls -l /dev/dpu
ls -l /opt/shadow/yolo_pose9/model/yolo_pose9_b4096.xmodel
ls -l /opt/shadow/yolo_pose9/runtime
systemctl status shadow-yolo-follow --no-pager
python3 -c "import numpy, cv2, xir, vart; print('VISION_IMPORT_OK')"
```

正常目标是 ARM64 环境，通常 `uname -m` 输出 `aarch64`。若临时服务不存在或未启动，不代表 Linux 没装；应先确认纯视频是否正常，再按视觉交接流程恢复 FOLLOW。依赖导入失败时记录具体报错，由视觉或系统负责人恢复匹配环境。

**本阶段完成标准：**确认当前 SD 基线可以启动；能进入板端 Linux；掌握当前视觉启动和停止方式；记录真实系统版本、设备和依赖状态。PetaLinux 的确切版本、完整构建环境及 SDK 可用性须由队友确认，不能只凭 Vivado 2022.2 推断。

<!-- PAGEBREAK -->

## 3 在电脑上复现总控软件

以下命令在电脑 Ubuntu 中执行，不会访问真实电机。WSL 与 VirtualBox 是两个独立环境；不要混用构建缓存。若使用 WSL，当前 Windows 目录一般对应下列路径；VirtualBox 应改为自己的工程位置。

```bash
cd /mnt/d/Desktop/piying/shadow_play
sudo apt update
sudo apt install build-essential cmake ninja-build pkg-config libasound2-dev python3
cmake -S . -B build-linux -G Ninja -DCMAKE_BUILD_TYPE=Debug -DSHADOW_REQUIRE_ALSA=ON
cmake --build build-linux --parallel 4
SHADOW_TEST_ALSA_NULL=1 ctest --test-dir build-linux --output-on-failure
```

先完成配置和编译，再运行程序。成功时应生成 `shadow_show`、`shadow_send`、`trace_preview` 和 `make_cue_wav`。依赖齐全、启用测试的 Linux 本机构建应包含文档所列 9 项 CTest；缺少 Python 时部分 Python 链路测试不会注册，需要补齐后重新配置。ALSA null 只验证软件调用，不等于验证扬声器播放。

依次运行以下场景。所有输出名都必须尚未存在；重复验证时把文件名中的 `01` 改成新的编号。

```bash
./build-linux/shadow_show --seconds 92 --output build-linux/rehearsal_01.csv
./build-linux/trace_preview build-linux/rehearsal_01.csv build-linux/rehearsal_01.svg
./build-linux/shadow_show --mode camera --seconds 4 --replay assets/camera_demo.jsonl --output build-linux/camera_01.csv
./build-linux/shadow_show --mode touch --seconds 4 --replay assets/touch_demo.jsonl --output build-linux/touch_01.csv
./build-linux/shadow_show --seconds 12 --commands assets/mode_session.csv --replay-at 3500 assets/touch_demo.jsonl --replay-at 7000 assets/camera_demo.jsonl --output build-linux/modes_01.csv
```

查看 CSV 中的 `angle_deg`、`input_state`、限位和限速标记；打开 SVG 对比目标角度与最终输出。90 秒剧本加 2 秒观察属于加速模拟，不会实际等待 92 秒。模式测试覆盖自动、暂停、恢复、触控、体感和停止。

**你应保存：**构建命令、测试结果、三种模式的输出、至少一张重新生成的轨迹图。此阶段的工作是验证你能复现现有软件并理解输出，不需要重写已具备的映射和通信模块。

<!-- PAGEBREAK -->

## 4 验证 Python 到 C++ 的通信

在同一台电脑、同一个 Ubuntu 环境中打开两个终端，二者都进入 `shadow_play`。当前网络接口固定为本机回环地址 `127.0.0.1`，不能直接让板上的视觉发给电脑端总控。

终端 A 先启动接收端，等待日志提示输入端口和控制端口就绪。

```bash
./build-linux/shadow_show --mode camera --seconds 60 --realtime \
  --listen 56000 --control-port 56001 \
  --record-input build-linux/udp_input_01.jsonl \
  --record-commands build-linux/udp_commands_01.csv \
  --motor-format jsonl --output build-linux/udp_motor_01.jsonl
```

终端 B 发送 5 秒合成九点数据。这条命令不打开摄像头，也不加载 DPU。

```bash
python3 integrations/follow/pose_sender.py --port 56000 --seconds 5
```

检查输入记录中 `source=camera`、`version=2`、递增的 `seq` 和固定的 `session_id`。电机输出应按控制周期包含整组轴，武松颈部和双手目标变化，老虎两根杆保持中立。发送结束后，在现有模拟策略下，各杆有效输入超时并限速回中。

重新运行发送器会产生新会话。若总控仍在运行，应先依次执行下面三条命令，再启动新的发送器；观察接收端是否接受各条命令。

```bash
./build-linux/shadow_send --port 56001 --command stop
./build-linux/shadow_send --port 56001 --command reset-inputs
./build-linux/shadow_send --port 56001 --command camera
```

录制结果可离线重放。输入记录是带 `arrival_ms/frame` 的 JSONL，电机输出是 `motor_targets` JSONL，二者不能互换。

```bash
./build-linux/shadow_show --mode camera --seconds 60 \
  --replay build-linux/udp_input_01.jsonl \
  --commands build-linux/udp_commands_01.csv \
  --output build-linux/udp_replay_01.csv
```

**完成标准：**明确看到发送、接收、映射、整组输出及超时处理；正确处理发送器重启。实时录制回放会受 Linux 调度影响，不要求浮点轨迹逐字相同。当前默认总控周期 20 ms，即 50 Hz，不代表视觉有 50 FPS。

<!-- PAGEBREAK -->

## 5 在板上接入真实 FOLLOW

**前置条件：**硬件队友已经提供能在现有板端 Linux 运行的 ARM64 总控程序；原 FOLLOW 能正常采集和显示；先使用 CSV 或 JSONL 后端。第一轮板端目标是“真实人体动作能生成正确角度数据”。

交给视觉队友的新增文件位于 `shadow_play/integrations/follow`：

- `pose_sender.py`：消息过滤、归一化和非阻塞 UDP 发送。
- `board_follow_with_sender.py`：已经加入发送调用的入口副本。

它们仍依赖 FOLLOW 原有的 `orientation.py`、`fast_decode.py`、`pipeline_input.py`、`display_queue.py`、`pose_responsive.py`，以及 `/opt/shadow/yolo_pose9/runtime` 和原模型。如果视觉队友此后更新过 FOLLOW，应把发送调用合入其新版代码，不用旧副本覆盖新功能。

由视觉队友按原部署方式正常停止旧入口，再放入上述文件。原交接使用 COM3 串口传输，端口、登录状态和串口独占由现场确认；不要同时运行两个占用摄像头和 HDMI 的入口。

若已经确认板端 C++ 程序在 `./build-arm/shadow_show` 且当前目录是包含 `assets/config` 的部署目录，可先运行：

```bash
./build-arm/shadow_show --mode camera --seconds 120 --realtime \
  --listen 56000 --control-port 56001 \
  --record-input /tmp/follow_input_01.jsonl \
  --motor-format jsonl --output /tmp/follow_motor_01.jsonl
```

另一个板端终端启动集成视觉入口。以下示例仅适用于全部 FOLLOW 文件已按交接放在 `/tmp`、旧服务已正常停止、基础环境完整的情况；先检查同名临时单元是否存在。

```bash
sudo systemd-run --unit=shadow-follow-control-test \
  --property=Restart=no --property=TimeoutStopSec=10 \
  /usr/bin/env PYTHONPATH=/opt/shadow/yolo_pose9/runtime:/tmp \
  /usr/bin/python3 -u /tmp/board_follow_with_sender.py --pose-port 56000
sudo journalctl -u shadow-follow-control-test -n 30 --no-pager
```

依次只抬左手、只抬右手、移动上身、遮挡腕点、离开画面并重新进入，核对输入与角度记录。结束时正常停止测试服务：`sudo systemctl stop shadow-follow-control-test`，确认恢复纯视频。把 `/tmp` 的记录导出到电脑保存；重启后这些临时文件可能消失。

<!-- PAGEBREAK -->

## 6 你必须掌握的数据和映射约定

**从视觉取数的位置：**`pose = stabilizer.update(...)` 之后。使用已选人、跟踪和防抖的最终 `pose`，不取原始 DPU 张量或每两秒输出的状态日志。

| 数据层 | 单位与方向 | 使用规则 |
| --- | --- | --- |
| FOLLOW pose | 9×3，像素 x、y、置信度 | 1280×720 正向图像，左上为原点 |
| camera v2 | x、y 为 0 到 1 | 适配器归一化，不再旋转一次 |
| 五杆目标 | x、y 为 -1 到 1 | x 向舞台右，y 向上，中立为 0 |
| 电机输出 | angle_deg，单位度 | 最终指令，不是位置反馈 |

九点顺序固定为头、左肩、右肩、左肘、右肘、左腕、右腕、左髋、右髋。左右是人体自身左右，必须通过单独抬手确认。视觉适配过滤阈值为 0.25，总控模拟控制阈值为 0.5；“画面上有点但电机目标不更新”可能由阈值差异造成。

camera v2 顶层字段严格为 `version/source/session_id/seq/track_id/captured_s/detected/points`。不要增加尚未约定的 width、height 等字段。一个 UDP 数据报包含一整帧；未检出人物仍发 `detected:false` 和空 points。缺失点不得用旧坐标伪装为新测量。

颈部杆使用双肩中点，双手使用同侧肩腕相对位置。简化公式如下，计算后限制到杆目标范围；水平镜像由统一配置处理。

```text
neck = (left_shoulder + right_shoulder) / 2
neck_x = neck_gain_x * (neck.x - neck_origin_x)
neck_y = neck_gain_y * (neck_origin_y - neck.y)
S = hand_span_shoulders * shoulder_width
hand_x = (wrist.x - shoulder.x) / S
hand_y = (shoulder.y - wrist.y) / S
```

双肩中点只能近似二维颈部平移，不能代表真实脖子转角。体感和触控模式下虎头、虎尾保持中立，剧本模式才编排全部五杆。

**异常行为要能解释：**同会话序号重复或倒退会被拒绝；新会话需 `stop → reset-inputs → camera`；换人后停止，确认人物再启用 camera；默认缺点保持 0.30 秒后限速回中。`captured_s` 是板端图像复制完成的单调时间，不是曝光时刻，也不能直接与其他设备时钟相减计算端到端延迟。

<!-- PAGEBREAK -->

## 7 把模拟参数换成实物标定

你负责维护两类配置：`retarget` 决定人体动作怎样变成杆目标；`calibration` 决定杆目标怎样变成各轴角度。先保留模拟配置，在新文件中记录实物参数。建议命名 `config/retarget.hardware.json` 和 `config/calibration.hardware.csv`，这些文件需要你们实际制作。

第一步，在固定演示机位、演员位置和自然站姿下记录双肩中点，填写 `neck_origin_x/y`。第二步，单独测试水平和竖直小幅运动，确认 `mirror_x` 与安装方向。第三步，调节颈部增益及手部比例，使有限人体动作覆盖实际需要的杆运动范围。

| retarget 字段 | 你的标定工作 |
| --- | --- |
| version | 保持本配置版本为 2 |
| confidence_threshold | 依据真实漏点和误检调整，并记录理由 |
| neck_origin_x/y | 写入实际自然站姿的双肩中点 |
| neck_gain_x/y | 调整上身位移对应的杆动作幅度 |
| hand_span_shoulders | 调整肩腕相对运动比例 |
| min_shoulder_width | 检查演员过远时的控制有效性 |
| mirror_x | 用实际左右动作验证镜像效果 |

每个实际电机轴在 calibration CSV 中独占一行。五根杆不等于五个电机，也不必然等于十个电机。硬件队友确认以下参数后，你再录入配置。

```text
axis_id,rod,neutral_deg,min_deg,max_deg,gain_x_deg,gain_y_deg,max_speed_deg_s,smoothing_tau_s
```

`axis_id` 对应真实通道；`rod` 使用五种规定名称；中立角、最小角、最大角来自机构实测；两个 gain 的正负反映安装方向；最大指令速度须经过测试；平滑时间常数越大，响应越慢。不要直接把示例里的 90°、限位或速度当作已验证参数。

现有映射为 `中立角 + gain_x × 杆x + gain_y × 杆y`，之后做角度限位、平滑和限速。这是局部线性模型。若出现明显非线性、回差、机构耦合或多杆相互干涉，应记录现象并与机械队友建立标定表或运动学模型；单纯放大增益无法解决。

**完成标准：**自然站姿对应期望初始姿态；左右和上下方向正确；单杆及组合动作在验证范围内；输出限速不导致关键动作持续跟不上。保留每次参数修改前后的轨迹、动作录像和版本号。最终需使用真实初始化后的已知指令作为映射初始值，不能假设上电时电机已经在中位。

<!-- PAGEBREAK -->

## 8 与硬件队友对接真实电机

你提供 `include/shadow/motor_backend.hpp` 和 `docs/hardware_motor_protocol.md`，硬件队友实现后端，并和你一起修改应用入口以选择真实后端。当前 `show_main.cpp` 只会创建 CSV 或 JSONL 后端，**仅修改标定文件或把程序拷到板上都不会驱动电机**。

接口为 `MotorBackend::send(const ControlTick&)` 和 `shutdown()`。每个周期遍历完整轴组，按 `axis_id` 匹配真实通道，发送最终 `angle_deg`。`limited_target_deg` 尚未完成全部平滑和限速，只能用于诊断。当前命令行没有已经实现的 `--motor-format hardware`。

请硬件队友按每轴返回以下内容，未知项保留待定，不能猜地址或默认使用某种舵机参数。

| 项目 | 必须提供的具体内容 |
| --- | --- |
| 轴与机构 | axis_id、所属杆、自由度、电机型号、实际通道 |
| 行程与方向 | 中立位置、角度上下限、正方向、可用动作范围 |
| 指令换算 | 角度到 PWM 脉宽或其他执行器量的关系 |
| 硬件接口 | 驱动 API 或设备文件；若为 AXI，提供寄存器说明 |
| 更新方式 | 全部轴如何成组生效，允许的更新频率 |
| 初始化 | 上电归位流程、初始指令、是否有位置反馈 |
| 异常处理 | 看门狗、失联动作、使能、停止、退出和急停 |

接入代码需要共同检查四个位置：硬件初始化是否先完成；映射器是否拿到已知初始指令；每周期是否发送完整有效轴组；异常退出是否执行约定的后端清理。若 PL 具有暂存与统一提交寄存器，应先写齐各轴，再统一提交。

软件 `stop` 的含义是按当前策略回中，`pause` 用于剧本暂停并保持指令，它们不等于硬件急停。程序卡死时软件超时逻辑也无法继续运行，必须由硬件队友确认独立的失联处理。具体保持、回中或去使能行为取决于实际机构。

**实物验证顺序：**硬件队友先独立验证单轴，再由你接低速、小幅总控指令；随后逐根杆、武松三杆、老虎两杆、五杆组合。首次接入按机构条件卸载或隔离负载，确认独立停机方式后逐步扩大幅度。每一步都记录预期动作、实际动作、参数和异常。

<!-- PAGEBREAK -->

## 9 制作正式剧本和音频

`assets/rehearsal90.json` 与 `assets/storyboard.csv` 是 90 秒模拟排练素材，需要你结合真实机构重新编排。建议先制作可稳定完成的短段，再扩展为整场；每次新动作先看曲线，再上机构验证。

分镜至少写清开始时间、结束时间、剧情、五根杆目标、旁白或音效提示。可以沿用“入场、老虎出现、交锋、结束、谢幕、回中”的现有结构，但动作幅度和节奏应按你们的正式表演确定。

剧本 JSON 的 `version` 保持 1，`duration_ms` 为总时长；frames 按时间排列，每帧给出全部五根杆的归一化二维目标。使用 `wusong_neck`、`wusong_left`、`wusong_right`、`tiger_head`、`tiger_tail`。同一帧不要同时出现新名和旧别名 `wusong_body`。

建议保存为 `assets/show_final.json`。预览示例中的 92 秒适用于 90 秒剧本加 2 秒结束观察；若更改剧本时长，同步调整运行时长。

```bash
./build-linux/shadow_show --script assets/show_final.json \
  --calibration config/calibration.hardware.csv \
  --seconds 92 --output build-linux/final_preview_01.csv
./build-linux/trace_preview build-linux/final_preview_01.csv build-linux/final_preview_01.svg
```

上面的电脑命令仍然只导出角度。检查目标与输出是否长期分离；若限速使动作错过剧情节点，应调整动作时间或幅度，而不是擅自放宽实物速度限制。

正式 WAV 需要 PCM16 单声道或双声道，与剧本时长相差不超过 1 ms。先用工具生成每秒提示一次的测试音，再用目标板真实音频设备检查同步；提示音不是正式配音。

```bash
./build-linux/make_cue_wav build-linux/cue90_01.wav 90
./build-linux/shadow_show --realtime --seconds 92 \
  --audio device --wav build-linux/cue90_01.wav \
  --output build-linux/audio_01.csv
```

最终音频可由剧本 `audio_file` 指定，路径相对剧本文件。你负责核对动作与台词、音效关键节点；硬件队友负责板端声卡和驱动。验收包含暂停、继续、结束、设备打开失败和播放异常；电脑 ALSA 编译成功不能代替板端扬声器测试。

<!-- PAGEBREAK -->

## 10 板端部署和开机流程

**ARM64 编译由硬件队友提供匹配 SDK，你负责给出固定源码、依赖和资源，并共同验证结果。** 电脑的 `build-linux` 通常是 x86 构建，不能直接复制到 XCZU4EV 执行。另建 `build-arm`，使用队友给出的 SDK 环境脚本和 CMake 工具链；SDK 路径尚未确认，不在这里编造命令。

交付二进制前应使用 `file` 确认架构，并在板上运行 `shadow_show --help` 检查加载器和动态库。板上先跑离线模拟，再跑真实视觉输入且只导出数据，最后接已经验证的电机后端。不要一开始就把所有功能改成自动启动。

建议与硬件队友统一如下持久目录。这是待落实的部署约定，不代表这些目录当前已存在。

```text
/opt/shadow/control/bin/        总控及辅助程序
/opt/shadow/control/config/     实物标定和重定向配置
/opt/shadow/control/assets/     正式剧本和音频
/opt/shadow/follow/             固定版本的 FOLLOW 及发送器
/var/log/shadow/                联调日志或约定的日志位置
```

总控默认使用相对路径，因此正式服务必须明确工作目录或通过 `--script`、`--calibration`、`--retarget` 指定绝对路径。启用实际音频还需正确的设备权限和 ALSA 库。程序资源路径、运行用户和权限应写进部署记录。

开机流程应由三人约定为：硬件及纯视频初始化成功；电机初始化并建立已知状态；总控启动到已确认的初始模式；视觉发布新输入；操作员确认受控人物后进入体感，或按操作流程启动剧本。是否需要人工确认以及启动时姿态，由实际机构和演示流程决定。

需要新增或完善的系统工作包括：把 FOLLOW 从 `/tmp` 安装到持久目录；制作正式 systemd 单元；确定服务依赖和退出顺序；定义视觉重启后的会话重置流程；管理日志文件名与容量。当前导出选项拒绝覆盖已有文件，反复自启动时不能固定重用同一个已存在的输出名。

**定版验收：**断电再上电，在不临时手传文件的条件下恢复约定功能；验证显示、输入、输出、音频及退出；保存 SD 基线、最终配置、源码和构建版本。建议连续做 3 次冷启动并记录结果，这是本轮建议的验收次数。保留可恢复的纯视频基线，不把历史 `sd_candidate` 名称本身当成最终验收证明。

<!-- PAGEBREAK -->

## 11 整机验收记录表

每项记录日期、软件版本、配置版本、操作者、现象和结果。失败项说明归属及下一步，修复后复测相关链路。表中“通过条件”是本轮验收目标，不是对现有实物状态的声明。

| 编号 | 场景 | 通过条件 |
| --- | --- | --- |
| A01 | 电脑构建与测试 | 测试完整运行且通过，命令和日志可复现 |
| A02 | 三种离线模式 | 剧本、触控、体感输出和切换符合定义 |
| A03 | 本机 UDP | 九点进入总控，生成完整轴组，无旧帧积压 |
| A04 | 真实左手与右手 | 角色对应手动作正确，不交换关键点 ID |
| A05 | 自然站姿及上身移动 | 颈部杆中位和运动方向正确 |
| A06 | 腕点或肩点遮挡 | 无效点不续期，对应杆执行已验证策略 |
| A07 | 人物离开和重新进入 | 不持续执行旧动作，换人需确认后启用 |
| A08 | 视觉进程重启 | 新会话被锁定，按重置流程恢复 |
| A09 | 重复序号或非法数据 | 拒绝异常帧，不刷新有效输入时间 |
| A10 | 单轴及五杆组合 | 轴通道正确，限位、方向、协调性可接受 |
| A11 | 停止与剧本暂停 | stop、pause、resume 的实物行为符合约定 |
| A12 | 程序失联或退出 | 硬件独立策略与退出行为得到验证 |
| A13 | 90 秒正式演出 | 动作、音频、终态符合正式分镜 |
| A14 | 连续运行 | 建议至少 10 分钟，记录卡顿、错误和温升现象 |
| A15 | 冷启动与恢复 | 建议 3 次成功，日志和回退流程可复现 |

整体时延应测“操作者动作到皮影动作”的实际效果，可用同时拍到两者的录像分析。DPU 约 15 ms 和历史空场约 28.6 FPS 都不能代替这一指标；视觉、通信、控制周期、平滑和机构响应都会产生延迟。

验收前由三人确定可接受的动作误差、延迟与演出稳定性标准，再填写实测值。当前资料没有足够依据给出统一的毫秒门限或实际电机角度精度。软件限速约束的是命令变化，不是电机实测速度。

<!-- PAGEBREAK -->

## 12 你的交付清单和推进顺序

**你现在可以独立完成：**电脑编译和测试、三模式回放、本机 UDP、输出格式核对、工作记录、正式分镜初稿。真实板端接口和机械参数未到齐前，这些任务仍可推进。

| 阶段 | 你要产出的成果 | 完成后再进入 |
| --- | --- | --- |
| 第一阶段 | 构建测试日志、三模式轨迹、UDP 输入和输出记录 | 板端只导出角度联调 |
| 第二阶段 | 真实视觉输入记录、左右及异常场景结果 | 接实际电机与标定 |
| 第三阶段 | 实物轴配置、重定向配置、单轴和组合录像 | 正式剧目调试 |
| 第四阶段 | 正式剧本、WAV、整场运行记录 | 持久部署与冷启动验收 |
| 第五阶段 | 固定版本交付包、启动停止指南、最终验收表 | 团队演示定版 |

建议交付包包含：完整 `shadow_play` 源码及 CMake；匹配的 ARM64 二进制及构建说明；视觉适配版本；实际 calibration/retarget 配置；正式剧本与 WAV；接口说明；测试及联调记录；启动、停止、重启和故障恢复步骤。SD 与硬件产物由硬件队友提供，并在最终版本表中与总控对应。

**需队友交付后才能完成的事项：**视觉队友提供当前真实 FOLLOW 与消息样本；硬件队友提供匹配 SDK、真实轴表、MotorBackend、PWM/驱动及上电归位和失联行为；三人共同确认演员机位、动作幅度、正式分镜和最终验收标准。

建议你第一轮就交出 4 份可检查成果：一份测试日志、一组摄像头模拟轨迹、一份 UDP 整组角度文件、一张待队友填写的实际电机轴参数表。这样讨论可直接围绕文件和现象进行。

### 资料定位

以下路径均相对 `D:\Desktop\piying`，可在工程中直接定位。

- 视觉现状与恢复：`handoff_visual_follow_20260922/交接说明.md`。
- 总控联调入口：`shadow_play/docs/vision_to_motor.md`。
- 输入字段与状态：`shadow_play/docs/input_protocol.md`。
- 发送器集成：`shadow_play/integrations/follow/example_hook.md`。
- 电机接口：`shadow_play/docs/hardware_motor_protocol.md`。
- 映射与标定：`shadow_play/docs/mapping.md`。
- 历史测试范围：`shadow_play/docs/validation.md`。

文中命令分为电脑模拟、板端只读检查和条件满足后的板端联调；执行前确认所在环境。既有 9/9 测试、视觉性能和部署状态来自交接记录，应按本手册重新完成你们这一轮的验收记录。
