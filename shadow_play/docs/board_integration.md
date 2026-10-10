# Zynq 板端总控联调记录

> 本页保留 10 月 3 日的历史记录。10 月 10 日 USB 摄像头迁移与最新启动文件状态见 [USB 摄像头迁移](usb_camera_migration.md)；下文“BOOT.BIN 未改动”等结论只对应当时操作。

本文件记录 2026 年 10 月 3 日对用户实物板的操作，供总控软件与整机联调负责人使用。ARM64 总控软件测试已通过，SD 卡只读配置已修正，程序与日志已保存到 SD 卡并通过软件重启验证。真人识别测试按用户要求暂缓，实际舵机仍不在本轮操作范围内。

程序保存下来、手动启动成功、整机开机自动运行是三个不同状态。本轮完成前两项；原视觉服务会自启，总控尚未集成进开机镜像。所有电机输出都是文件中的计算角度，没有连接真实舵机后端。

## 已确认的板端环境

| 项目 | 本次实测 |
| --- | --- |
| 调试入口 | PS 串口当前 COM9，115200，8N1；重新插接前为 COM3 |
| 系统 | PetaLinux 2022.2，Linux 5.15.36-xilinx-v2022.2，aarch64 |
| 运行库 | glibc 2.34，libstdc++.so.6.0.29 |
| Python 与视觉 | Python 3.9.9，NumPy 1.21.2，OpenCV 4.5.2；xir、vart 可导入 |
| 模型 | `/opt/shadow/yolo_pose9/model/yolo_pose9_b4096.xmodel`，与交接校验值一致 |
| 视觉入口 | `/opt/shadow/yolo_pose9/follow/board_follow.py`，与本地冻结交接版本一致 |
| 启动方式 | `shadow-video.service` 初始化视频，`shadow-yolo-follow.service` 通过 `boot_guard.py` 启动 FOLLOW |
| 文件系统 | `root=/dev/ram0`；根目录与 `/tmp` 内容不能据此认定断电持久保存 |
| SD 卡 | 修正后 `ro=0`，FAT 第一分区及 ext4 第二分区均以 rw 挂载；第二分区约 26.2 GiB 可用 |
| 网络 | 本次仅发现 lo、sit0，没有可用 Ethernet 接口；使用串口传输 |
| 音频 | 本次未发现可用声卡和目标 ALSA 库，ARM64 包使用静音时钟 |

板端时钟显示 2023 年 3 月 4 日，与实际工作日期不符。证据目录中的 `20230304` 来自板端时钟；它们确实是本次采集。程序的实时调度和输入时间使用单调时钟，不依赖该日历日期。

## 已完成的工作及其范围

1. 备份板端 FOLLOW、runtime、视频初始化程序和 systemd 服务。没有覆盖 BOOT.BIN、image.ub、原始模型或原始视觉入口。
2. 使用本机 Vitis 2022.2 自带 aarch64-linux-gnu GCC 11.2.0 交叉编译 C++17 总控。ELF 为 AArch64，依赖与实物板相符，已实际执行。
3. 完成板端自动软件验证，共 17 个执行步骤通过。包含五组 C++ 行为测试、Python 发送器、FOLLOW 模拟数据到 C++ 的链路、实际 UDP 收发、四个演示场景与轨迹生成、录制回放一致性。
4. 90 秒排练加 2 秒结束观察，产生 46010 行十轴计算结果，检查角度范围和速度限制。该测试是加速软件排练，不是实际持续 92 秒的机构表演。
5. 实际启动摄像头、DPU、HDMI、Python 发送器与 C++ 总控。约 56.7 秒内收到 1620 帧，非法消息、重复消息、生命周期拒绝均为 0。

第 5 项的 1620 帧均为 `detected=false`，所有输出角度保持示例中位 90 度。它证明“未检出人体”状态能够传到总控，不能作为抬手跟随成功的证据。发生故障前，周期日志的显示帧率平均约 28.59 FPS；这不是相机到舵机的端到端延迟。

暂停真人测试后另完成以下工作：

1. 修正启动设备树的 SD 写保护配置，写入并回读校验探针文件；正常软件重启后再次验证可写、文件和测试记录仍在。
2. 将 23 个运行文件安装到 `/run/media/mmcblk0p2/piying/shadow-board-20261003`，逐文件 SHA-256 校验通过；重启后重新核对通过。
3. 增加 `tools/board_control.py`，可启动、查询和停止有限时长的总控进程，可发送 script、touch、camera、stop、reset-inputs 命令。该工具使用临时 systemd 服务，不采集摄像头，不调用真实电机驱动。
4. 在实物板进行 20 秒实时测试，模拟发送 90 帧人体关键点，全部接收，产生 10010 行角度记录；双手轴变化、输入消失后回中、虎杆中立、角度及速度限制均通过。随后单独验证 script → touch → script 与主动终止，正常退出；重启后再次启动短时 script 验证。
5. 修复 CSV 核查器对六位小数时间戳舍入的误报。误差上界按“限速 × 1 微秒 + 1 微度”计算，控制器的实际限速算法未改。新增 3 个回归用例，既接受实测舍入例子，也拒绝超出舍入范围的速度偏差和非递增时间。

这些模拟关键点由程序生成，不是摄像头识别结果。本轮模拟中双肩不移动，因此颈部保持中立；颈部随双肩中点变化的逻辑已在此前 FOLLOW 链路测试中验证。

## 本轮发现的问题

### 摄像头采集错误使骨架程序退出

原始 FOLLOW 在接入总控前就已失败。重新初始化后能恢复运行，但再次出现 `Camera DMA error`、`Pose drain DMA error`，以及状态 `0x15100`；真人联调最终出现 `0x15190`。用户同时观察到有画面而无骨架、后来画面冻结或异常。

`0x15100` 中的 bit 8 是 EOLEarlyErr，表示实际输入行比配置长度短。`0x15190` 还带有帧尺寸相关错误位。寄存器含义见 [AMD AXI VDMA 状态寄存器说明](https://docs.amd.com/r/en-US/pg020_axi_vdma/S2MM_VDMASR-S2MM-VDMA-Status-Register-Offset-34h)。目前不能仅凭这些位断定线缆、电源、传感器或 PL 时序中的哪一项是根因。

用户确认摄像头使用杜邦线，已经断电检查插接并重新上电。之后观察到原视觉服务持续运行超过 11 分钟，期间未再发现此前的 DMA 退出；后续重启也能启动原视觉服务。这个无人配合的观察尚不能证明采集故障已彻底排除。用户目前只有一人、不方便固定摄像头，真人骨架与抬手验收暂缓。程序保留 DMA 错误检查。

### SD 配置已修正并完成持久部署

首轮 SD 被识别为整卡只读，应用只能放在 RAM。检查发现本地硬件工程关闭了 SD1 写保护引脚，而板端设备树缺少 `disable-wp`。该属性的含义可在 [Xilinx 2022.2 MMC 设备树绑定](https://raw.githubusercontent.com/Xilinx/linux-xlnx/xlnx_rebase_v5.15_LTS_2022.2/Documentation/devicetree/bindings/mmc/mmc-controller.yaml) 中核对。

曾尝试在 Linux 内添加 overlay 并重新绑定 SD 驱动；卡的只读标志消失，但随后触发内核空指针 panic。用户已协助断电重启恢复。**该在线卸载重绑方法不再使用。**现方案在 U-Boot 加载原镜像并校验后，只修改交给 Linux 的工作设备树，再正常启动；实测重启成功，没有再使用在线驱动切换。

持久改动是 SD 第一分区新增 `uEnv.txt`，由原 `boot.scr` 读取。BOOT.BIN、image.ub、boot.scr 均保持原始哈希。第二分区新增 `piying` 目录存放运行包、输出和备份，没有切换到该分区已有的旧 rootfs。Linux 的 `/` 仍来自 RAM；修改 `/etc`、`/home` 并不因此变成持久保存。

本轮做的是正常软件重启验证；新增配置后没有要求用户再次物理断电。日后有条件时仍应补一次断电启动验收。

若要撤销 SD 启动修正，在板端 root shell 执行以下命令，再正常重启；原镜像无需恢复。撤销后可能重新出现整卡只读，程序文件仍在第二分区，但可能不能正常挂载。

```sh
mv /run/media/mmcblk0p1/uEnv.txt /run/media/mmcblk0p1/uEnv.disabled-20261003.txt
sync
reboot
```

如果 Linux 无法启动，可在另一台电脑读取 SD 第一分区，将 `uEnv.txt` 改名；不要格式化卡。备份及原始哈希位于第二分区 `piying/boot-backup-20261003`，本机也保留了启动日志、原始 DTB 和新增配置。

### 声音和触控仍需相应硬件

静音时钟、WAV 格式与剧本软件逻辑已验证；实物板没有验证扬声器输出。触控协议与三模式切换有软件测试，但没有实际触摸屏事件输入或图形控制界面验收。

## 后续如何复测

### 现在可以独立完成的模拟运行

以下命令在板端 root shell 执行，普通用户先执行 `sudo -s`。不需要真人或移动摄像头；输出写 SD 卡，程序默认 92 秒后结束。

```sh
cd /run/media/mmcblk0p2/piying/shadow-board-20261003
python3 tools/board_control.py start --mode script --seconds 92
python3 tools/board_control.py status
# 提前停止整个总控进程
python3 tools/board_control.py stop
```

要模拟关键点跟随，可改用如下步骤。发送器运行约 3 秒后退出，总控继续运行至 20 秒，期间输入超时后回中。这个 camera 模式只表示总控接收人体关键点，不会自动打开真实摄像头或启动视觉发送器。

```sh
python3 tools/board_control.py start --mode camera --seconds 20
python3 follow/pose_sender.py --seconds 3
python3 tools/board_control.py status
```

每次输出放在新的 `output/controller-*` 目录，`output/latest-controller.json` 指向最近一次。目录内含 `session.json`、`controller.log`、`angles.csv`、`inputs.jsonl`、`commands.csv`。同一时间只允许一个总控占用 UDP 56000/56001；不要同时运行该入口和下面的真人采集入口。

运行中的模式可通过 `python3 tools/board_control.py command touch` 等命令切换。`command stop` 是进入停止模式并按策略回中，进程继续运行；`board_control.py stop` 是终止软件进程。两者都不是实物急停，均不发送真实舵机命令。

### 等摄像头固定后再做的真人联调

摄像头和 HDMI 应在开机前连接好。先确认总控已停止，原视觉服务和测试入口不能同时占用视频。

```sh
cd /run/media/mmcblk0p2/piying/shadow-board-20261003
python3 tools/board_control.py stop
systemctl stop shadow-yolo-follow.service
systemctl restart shadow-video.service
python3 -u tools/board_live_check.py --seconds 180
```

脚本启动总控后启动合入发送器的 FOLLOW，记录 `output/board-live-*` 中的 `vision.log`、`controller.log`、`inputs.jsonl`、`commands.csv`、`angles.csv` 和 `summary.json`。输出后端固定为 CSV，音频固定为静音时钟。180 秒结束后停止视觉，再留出时间观察输入消失。

真人应完整露出头、双肩、双手，先静止、分别抬手，再离开画面约 3 秒。程序发生人物跟踪切换时，总控会停止并等待重新选择 camera；视觉进程重启导致会话变化时，需要依次执行 stop、reset-inputs、camera。这些行为必须从日志确认，不能只看发送工具返回成功。

```sh
./bin/shadow_send --port 56001 --command camera
# 仅在视觉会话确实重启、需要重新接纳输入时：
./bin/shadow_send --port 56001 --command stop
./bin/shadow_send --port 56001 --command reset-inputs
./bin/shadow_send --port 56001 --command camera
```

验收应同时满足：存在有效人体关键点；抬左、右手改变正确的计算轴；无人时按配置超时回中；虎头尾保持中立；无非法协议帧；摄像头持续运行且无 DMA 错误。换人保护、软件丢人回中与实际机构安全是不同层次的验证。

## 分工与剩余交付

| 工作 | 我可以继续完成 | 需要你或队友提供 |
| --- | --- | --- |
| 板端程序 | 编译、传输、日志分析、测试、打包、可恢复的部署脚本 | 板卡供电和连接 |
| 摄像头稳定性 | 读取状态、对照代码和时序、对比冷启动及不同接线的结果 | 断电插拔、可靠短线、稳定供电、必要时示波器或 ILA 硬件采样 |
| 真人映射 | 分析真实关键点、确认左右和角度趋势、丢人/换人/重启测试 | 站到镜头前按动作配合；确认实际皮影左右约定 |
| 持久部署 | 文件保存、可回滚启动修正、正常重启已验证；后续将总控及视觉适配器集成进正式 rootfs，并做整机开机验收 | 最终镜像/工程版本确认；有条件时配合断电启动复测 |
| 界面与触控 | 在接口明确后实现控制界面和事件适配 | 触控屏型号、连接方式、操作流程需求 |
| 音频 | 整理 WAV、验证时长、构建音频后端、处理播放同步 | 声卡/功放/扬声器连接、最终配音和音效 |
| 正式剧目 | 按分镜编写动作数据并生成预览 | 最终故事分镜、动作要求、旁白和节奏确认 |
| 舵机与机械 | 后续可根据实测参数实现软件接口；本次未操作 | 实际轴数、协议、供电、归位、角度边界与机构标定；需另行开展实物联调 |

示例十轴和 90 度中位仍是模拟配置。CSV 的 `angle_deg` 是每个控制周期计算出的最终绝对目标角度，不是已测得的电机角度，也不是让舵机在当前位置再转相应角度。

## 证据与复现工具

本机证据目录：`D:\Desktop\piying\联调结果\Zynq_20261003`。

- `board-original-visual.tar.gz`：原视觉及服务备份。
- `board-results-20261003.tar.gz`：板端测试与真人联调原始结果，SHA-256 为 `cf9346125275007513145d99687621fbf2629b82e1fe90925071c545f39ba1c2`。
- `board-results/output/target-check-*`：17 步测试结果与轨迹。
- `board-results/output/board-live-*`：本轮未通过的真人联调证据。
- `report-metrics.json`：依据原始记录计算的数量和角度范围。
- `38-persistent-boot.log`、`39-reboot-persistence-pass.log`：新增启动配置自动应用及重启持久性证据。
- `36-controller-session-passed.log`：90 帧模拟输入、10010 行输出及服务生命周期核查。
- `deployment-results-20261003.tar.gz`：本轮三个进程管理测试的完整输出、重启后的视觉和内核日志、运行文件清单及 `uEnv.txt`；本机解压目录为 `deployment-results`。已校验与板端归档一致，SHA-256 为 `e7bda72e79be363a4d0bad3c35b4be997b46c19ee3c59682fe00212ed7f78765`。
- `shadow-board-runtime-20261003.tar.gz`：最终运行恢复包，SHA-256 为 `27f571f15027e846ac7cfa6d0c640f48475bb291769a1acfe0c424d847bc66d3`。板端同一文件保存在第二分区 `piying/shadow-board-runtime-20261003-final.tar.gz`；首次部署的旧归档保留作历史记录。
- `22-sd-overlay-test.log`：在线重绑导致 panic 的证据，保留供排查，不应按该路径复做。
- `tools/toolchain-vitis-aarch64.cmake`：Windows 上使用 Vitis 的 ARM64 工具链。
- `tools/target_check.py`：目标 Linux 上运行已编译的全套软件检查。
- `tools/board_live_check.py`：真实视觉与 CSV 总控采集。
- `tools/board_serial.ps1`：已登录串口中的命令执行与日志保存。
- `tools/board_transfer.ps1`：经串口传输简单 `/tmp` 文件，接收方校验哈希并拒绝覆盖。
- `tools/board_login.ps1`：按串口提示登录并进入 root，不把密码存到文件。
- `tools/board_control.py`：SD 目录中的总控进程管理，不是开机自启服务。

## Windows 交叉编译与传输

当前电脑的工具位置已实测。以下命令在项目根目录 `D:\Desktop\piying\shadow_play` 的 PowerShell 中执行：

```powershell
& 'D:\Program Files (x86)\STM32CubeCLT_1.19.0\CMake\bin\cmake.exe' `
  -S . -B build-arm64-vitis -G Ninja `
  '-DCMAKE_MAKE_PROGRAM=D:/Program Files (x86)/STM32CubeCLT_1.19.0/Ninja/bin/ninja.exe' `
  '-DCMAKE_TOOLCHAIN_FILE=D:/Desktop/piying/shadow_play/tools/toolchain-vitis-aarch64.cmake' `
  '-DVITIS_AARCH64_ROOT=D:/xilinx/Vitis/2022.2/gnu/aarch64/nt/aarch64-linux' `
  -DCMAKE_BUILD_TYPE=Release -DSHADOW_ENABLE_ALSA=OFF -DBUILD_TESTING=ON
& 'D:\Program Files (x86)\STM32CubeCLT_1.19.0\CMake\bin\cmake.exe' `
  --build build-arm64-vitis --parallel 4
```

Windows 不能直接运行这些 ARM64 Linux 可执行文件。完整测试包为证据目录下的 `shadow-board-tests-20261003.tar.gz`；较小的 `shadow-board-runtime-20261003.tar.gz` 仅带运行工具、FOLLOW、配置和真人采集脚本，不带 C++ 测试二进制。

串口传输要求板端已经登录 shell，且其他串口工具释放当前 COM9。COM 编号可能随 USB 插口改变，应按设备管理器确认。目标文件必须尚不存在：

```powershell
.\tools\board_transfer.ps1 `
  -PortName COM9 `
  -Source '..\联调结果\Zynq_20261003\shadow-board-runtime-20261003.tar.gz' `
  -Target '/tmp/shadow-board-runtime-20261003.tar.gz'
```

需要恢复到临时目录时，可在板端解压；本轮正式运行目录已经在 SD 上，不必重复安装。不要把不同版本覆盖混在同一目录；包根目录名为 `shadow-board-20261003`：

```sh
test ! -e /tmp/shadow-board-20261003 && \
tar -xzf /tmp/shadow-board-runtime-20261003.tar.gz -C /tmp
```

正式镜像集成应使用对应 PetaLinux 工程和目标依赖，不能照搬主机的 ALSA 库。当前运行包保留静音音频，不会自动启用真实电机。
