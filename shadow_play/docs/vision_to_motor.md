# 视觉 → 你的 C++ → 硬件队友：v0.3 联调与交付

## 1. 本版采用的五根杆

| 标识 | 真实连接位置 | 摄像头模式的数据来源 |
|---|---|---|
| wusong_neck | 武松脖子处，带动上身 | 两肩中点；触控可直接提供 neck |
| wusong_left | 武松左手 | 左腕相对左肩的位置 |
| wusong_right | 武松右手 | 右腕相对右肩的位置 |
| tiger_head | 老虎耳朵处的头杆 | 当前中立，由剧本模式另行编排 |
| tiger_tail | 老虎尾巴 | 当前中立，由剧本模式另行编排 |

武松不是通过骨盆杆控制。FOLLOW 没有直接的颈部点，C++ 使用双肩中点作为颈部平移参考；这不等于识别头部旋转。腿部不新增主动输出，继续依靠机构和惯性。

本版核心是 C++17；额外提供一个小型 Python 适配器，放入队员二现有 Python 视觉程序中发送数据，不需要把识别程序重写为 C++。

```text
队员二的摄像头 / DPU / FOLLOW
    ↓ 最终 pose：None 或 9×3，正向1280×720像素
pose_sender.py
    ↓ 过滤无效点、归一化、v2消息、非阻塞本机UDP
你的 shadow_show（PS Linux上的C++进程）
    ↓ 解析、来源/会话/帧号/人物检查
Retargeter
    ↓ 双肩中点→颈部杆，双腕→双手杆，虎头尾→中立
MotionMapper
    ↓ 每轴标定、限位、平滑、限速、输入超时
MotorBackend::send(ControlTick)
    ↓ 最终 angle_deg；可用JSONL查看整组命令
硬件队友实现的真实后端 / 驱动
    ↓ 按实测参数换算为PWM或真实执行器命令
PS/PL AXI接口 → PL输出 → 电机/云台 → 五根杆
```

Python 到 C++ 这一段是在 PS Linux 内进程间传递小型消息，不需要把九点坐标再送到 FPGA 做一次解析。PS 到 PL 的实际寄存器和驱动由硬件队友确定。

## 2. 先在你电脑的 Ubuntu 验证

先进入本次源码包里的 `shadow_play` 目录；以下命令都在这个目录执行。VirtualBox 内使用你实际解压的位置，不要照抄 WSL 的 `/mnt/d` 路径。

### 第一步：准备依赖并编译

```bash
sudo apt update
sudo apt install build-essential cmake ninja-build pkg-config libasound2-dev python3
cmake -S . -B build-linux -G Ninja -DCMAKE_BUILD_TYPE=Debug
cmake --build build-linux --parallel 4
cd build-linux
ctest --output-on-failure
cd ..
```

Python 适配器不需要安装 NumPy、OpenCV 或额外 pip 包；真实视觉程序自己的依赖仍由队员二提供。

### 第二步：回放一份摄像头示例

```bash
./build-linux/shadow_show --mode camera --seconds 4 \
  --replay assets/camera_demo.jsonl --output build-linux/camera_v03.csv
./build-linux/trace_preview build-linux/camera_v03.csv build-linux/camera_v03.svg
```

此示例是人工生成的九点数据，包含手腕置信度下降和人物丢失。输出使用 `wusong_neck_pan/tilt`，老虎头尾保持中立。

输出工具拒绝覆盖已有文件；重复演练时换一个文件名。

### 第三步：生成交给硬件队友看的命令样例

```bash
./build-linux/shadow_show --mode camera --seconds 4 \
  --replay assets/camera_demo.jsonl --motor-format jsonl \
  --output build-linux/motor_targets_v03.jsonl
```

这个 JSONL 每行是一个完整控制周期，含所有已配置电机轴的最终 `angle_deg`。十轴只是模拟配置，不是实际轴数结论。

`trace_preview` 读取的是 CSV，不能直接拿这个电机 JSONL 画图。输入回放 JSONL 和电机输出 JSONL 也有不同结构，不可混用。

### 第四步：两个终端测试 Python → C++ 的实际通信

终端 A，先启动 C++，观察输入端口就绪：

```bash
./build-linux/shadow_show --mode camera --seconds 60 --realtime \
  --listen 56000 --control-port 56001 \
  --record-input build-linux/follow_received_v03.jsonl \
  --motor-format jsonl --output build-linux/follow_motor_v03.jsonl
```

终端 B，同一个 Ubuntu 环境、同一源码目录：

```bash
python3 integrations/follow/pose_sender.py --port 56000 --seconds 5
```

这是合成九点输入，不打开摄像头，也不启动 DPU。发送结束后，C++ 继续运行；旧输入超时后按模拟参数限速回中。

每次重新运行 Python 命令都会生成新的会话。因此下一次演示前，在终端 B 执行：

```bash
./build-linux/shadow_send --port 56001 --command stop
./build-linux/shadow_send --port 56001 --command reset-inputs
./build-linux/shadow_send --port 56001 --command camera
python3 integrations/follow/pose_sender.py --port 56000 --seconds 5
```

端口日志和统计写在 stderr，电机 JSONL 写在指定文件，不会把日志混进消息数据。

## 3. 把哪些东西交给视觉队友

交付整个源码包，重点告诉他看：

- `integrations/follow/pose_sender.py`：逐帧适配和发送。
- `integrations/follow/board_follow_with_sender.py`：已合入发送调用的 FOLLOW 入口副本，与发送器一起放到原有最新 FOLLOW 运行目录；仍依赖队友原有视觉模块和板端环境。
- `integrations/follow/example_hook.md`：接入最新版 FOLLOW 的位置和完整步骤。
- `docs/input_protocol.md`：v2 格式、左右语义、有效性、会话和换人规则。

他应在最新 FOLLOW 的 `stabilizer.update` 后发送本帧数据，包括 pose=None 的帧；在主循环外创建一次发送器，程序退出时关闭。不要从每两秒的 `YOLO_STATUS` 取动作，也不要启用旧的 JSONL runtime 代替 FOLLOW。

只抬左手、只抬右手、左右/上下移动上身、遮挡肩/腕、离开画面并重新进入，分别录下实际消息用于验证。摄像头显示的 0.25 阈值与 C++ 的 0.5 控制阈值不同，要按实际误检和丢点情况调节。

双肩中点不在画面 (0.5,0.4) 时，先用自然站姿读数更新 `config/retarget.simulation.json` 中的 `neck_origin_x/y`，再调增益。配置示例不是实物标定文件。

## 4. 你的输出怎样交给硬件队友

优先接入方式：硬件队友实现 `include/shadow/motor_backend.hpp` 的 `MotorBackend`，在 `send(const ControlTick&)` 中遍历整组轴，读取每个 `axis_id/rod/angle_deg`。

他需要在真实应用入口替换当前 CSV/JSONL 导出后端，并用初始化/归位得到的已知指令值初始化映射器，不能直接使用模拟入口默认“每轴已经在中立位”的假设。

另一种参考方式：使用你生成的 `motor_targets_v03.jsonl` 核对组帧结构、轴名、单位和方向。如果他采用独立电机服务，可基于此格式实现实时接收；当前 JSONL 文件导出本身没有控制任何硬件，也不应把整份历史日志无节制回放给电机。

详细结构及职责见 `docs/hardware_motor_protocol.md`。PWM周期、角度到脉宽、AXI地址、更新/提交寄存器、设备文件和故障反馈目前没有硬件数据，不能凭空填写。

需要他返回的最小参数表：

| 参数 | 用途 |
|---|---|
| 每根杆的真实轴数、axis_id、硬件通道 | 将软件命令准确分配到电机 |
| 每轴中立角、最小/最大角、正方向 | 替换模拟标定 |
| 颈部杆、双手、虎头耳部杆、尾杆的有效移动范围 | 验证杆目标到角度的增益和机构耦合 |
| 指令速度上限、更新频率 | 调整限速和控制周期 |
| angle_deg 到执行器量的换算、成组生效方式 | 实现 MotorBackend 和 PWM/AXI |
| 上电归位、停止、失联/退出、急停行为 | 定义真实系统生命周期 |

## 5. 三个人本轮各做什么

| 人员 | 本轮任务 |
|---|---|
| 视觉队友 | 把发送器接入实际 FOLLOW，确认左右和置信度，提供真实录像消息；触控端另提供 neck/双肩/双腕 |
| 你 | 维护 v2 接收、颈部/双手映射、配置和脚本；电脑验证并交付 C++ 源码、Python 适配、资源和说明 |
| 硬件队友 | 合并板上软件，匹配 SDK 编译 ARM64，接真实 MotorBackend，完成 PWM/AXI、PetaLinux 和 SD 卡部署 |
| 三人共同 | 在机构上确认自然站姿、方向、动作幅度和速度，再完成实际皮影联调 |

本轮没有替你们制作最终配音/WAV，也没有把板卡未知的电机参数当成已确认值。

## 6. 从旧版迁移时注意

- 全新输出和配置使用 `wusong_neck`；C++ 枚举 `WusongBody` 与旧字符串 `wusong_body` 作为旧脚本/标定输入别名保留，同一帧不能同时放两个别名。
- `pelvis` 在消息里仍可被记录，但不会再驱动武松任何杆。
- 重定向配置升级为 `version=2` 和 `neck_*` 字段。旧 `body_*` 配置会报错，需明确迁移并重新标定原点。
- 输入消息 v2、重定向配置 version 2、电机 JSONL version 1、剧本 version 1 是不同文件/接口各自的版本，不能统一机械地改成同一个数。
- 旧 `output` 目录的图是历史产物，重新运行本版命令可生成新的颈部轴轨迹。
- 新源码包不含 x86 可执行文件、模型、BOOT.BIN、image.ub 或真实电机驱动。硬件队友继续使用其匹配的视觉运行环境和板卡工程。
