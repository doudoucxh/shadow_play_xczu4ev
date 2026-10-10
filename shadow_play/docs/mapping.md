# 皮影戏共用坐标映射核心

这是三种输入共用的 C++17 映射核心：接收五根控制杆的目标姿态，输出配置中每个电机轴的目标角度。代码只有标准库依赖，既可在电脑模拟，也可交叉编译进 XCZU4EV 的 Linux 应用。

**目前是可运行的算法初版。示例 CSV 的全部角度、轴数和速度都是模拟参数，未经任何实物标定。演示程序仅打印数据，不访问电机、PWM、AXI 寄存器或设备文件。**

## 文件位置

| 文件 | 作用 |
| --- | --- |
| `include/shadow/motion_mapper.hpp` | 队友可直接阅读的输入、输出和调用接口 |
| `src/motion_mapper.cpp` | 映射、限位、低通平滑、速度限制和输入超时 |
| `include/shadow/calibration_csv.hpp`、`src/calibration_csv.cpp` | 严格读取并校验标定参数 |
| `config/calibration.simulation.csv` | 仅用于模拟的参数；每行一个电机轴 |
| `src/demo.cpp` | 8 秒模拟运行，打印 CSV 轨迹 |
| `tests/mapper_tests.cpp` | 映射方向、边界、丢帧、时序等 19 组行为测试 |
| `docs/interface.md` | 三种上游输入和队员一电机模块如何对接 |

## 在 Ubuntu 编译和运行

需要 C++17 编译器、CMake 3.16 或更新版本；不需要先安装 PetaLinux SDK。

```bash
sudo apt update
sudo apt install build-essential cmake
```

在 `shadow_play` 目录执行：

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Debug
cmake --build build --parallel
ctest --test-dir build --output-on-failure
./build/mapper_demo config/calibration.simulation.csv > build/demo_output.csv
```

模拟时间按程序给定时间戳推进，因此不会实际等待 8 秒：0～4 秒生成五根杆的目标，2～2.2 秒故意发送越界的武松右手目标，4 秒以后停止发送新帧，超过保持时间后各轴限速回到中立目标。查看输出：

```bash
head -n 12 build/demo_output.csv
tail -n 12 build/demo_output.csv
```

输出列：

| 列 | 含义 |
| --- | --- |
| `time_s` | 模拟时间（秒） |
| `axis_id`、`rod` | 电机轴及所属控制杆 |
| `angle_deg` | 完成所有限制后的输出指令；以后交给电机接口的是这一列 |
| `limited_target_deg` | 角度限位后的目标，用于调试；尚未做平滑和速度限制 |
| `input_state` | `no_input` 无有效输入；`tracking_or_holding` 跟踪或短暂保持；`returning_to_neutral` 超时回中 |
| `input_clamped` | 输入坐标曾超出 [-1,1] |
| `angle_limited` | 计算角度触及标定范围 |
| `speed_limited` | 本次输出变化受到最大角速度限制 |

## 输入是什么

`ShadowPose` 有武松脖子处、左手、右手以及老虎头部耳朵处、尾巴处五个控制杆目标。规范标识分别为 `wusong_neck`、`wusong_left`、`wusong_right`、`tiger_head`、`tiger_tail`。旧 `wusong_body` 仅作为颈部杆的解析兼容名保留。每根杆用 `(x,y,valid)` 表示：

- `(0,0)` 是该杆标定的中立目标；`x` 向舞台右侧为正，`y` 向上为正。
- `x`、`y` 各为 [-1,1]，是约定的杆目标，不是像素、毫米或电机角度。
- 左右手名字按武松角色自身区分；摄像头镜像要在上游统一。
- `valid=false` 或非有限数（NaN/Inf）表示这根杆此次没有可用数据。默认构造的五根杆全部无效。
- 有限但越界的坐标会截断到 [-1,1] 并在输出中报告。

剧本播放器、触控和人体姿态适配器要先生成这一格式。重定向、肩宽归一化、置信度筛选和镜像已由上游 `Retargeter` 实现，不在 `MotionMapper` 内重复处理。五杆机械可达性/碰撞约束仍未实现。

`from_unit_screen(x,y)` 只把已经选好的杆目标点从左上原点的 [0,1] 坐标变成上述坐标：`x'=2*x-1`，`y'=1-2*y`。它不是完整的人体姿态映射。

### 颈部与双手重定向

最新 FOLLOW 提供双肩、双腕等九个关键点，没有直接检测的颈部点。C++ 用有效双肩的中点近似颈部；如果触控输入直接提供有效 `neck` 点，可使用该点。骨盆不再用于主杆。双肩中点只确定颈部杆位置，不能从 2D 关键点恢复颈部深度或真实转角。

对归一化后的颈部点 `(nx,ny)`：

```text
颈部杆x = 镜像方向 * neck_gain_x * (nx - neck_origin_x)
颈部杆y = neck_gain_y * (neck_origin_y - ny)
```

上述结果再截断到杆目标的 `[-1,1]` 范围。

左腕相对左肩、右腕相对右肩，除以 `hand_span_shoulders * 肩宽` 得到双手杆目标；这仍是待实物调节的局部映射。双肩无效或肩宽过小时无法建立可靠的相对尺度，对应手杆不刷新。

`config/retarget.simulation.json` 现在使用 `version: 2`、`neck_gain_x/y` 和 `neck_origin_x/y`；模拟站姿颈部参考点是 `(0.5,0.4)`。直接构造 C++ `RetargetConfig{}` 的默认参考点为 `(0.5,0.5)`，实际集成应显式加载/提供自己的标定配置。上述重定向配置版本与剧本版本、camera 消息版本是各自独立的协议。具体字段见 [输入协议](input_protocol.md)。

当前触控/摄像头模式中的虎头和虎尾保持中立；它们不会被人体头点或臀部点自动驱动。

## 映射算法

每个轴独立配置：

```text
raw_angle = neutral_deg + gain_x_deg * x + gain_y_deg * y
target = clamp(raw_angle, min_deg, max_deg)
dt = min(本次与上次控制更新的真实时间差, max_step_s)
alpha = 1 - exp(-dt / smoothing_tau_s)       # tau=0 时禁用低通平滑
requested_delta = alpha * (target - 上次输出角度)
delta = clamp(requested_delta, -max_speed_deg_s*dt, +max_speed_deg_s*dt)
本次输出角度 = 上次输出角度 + delta
```

同一根杆可对应一个、两个或更多配置轴，不要求固定十路。`gain_x_deg`、`gain_y_deg` 的正负处理安装方向；两个增益都非零时支持该轴对两个输入分量的局部线性响应。

**这是初始局部线性模型，不能代替任意连杆机构的逆运动学。**机构耦合、非线性或回差明显时，需要实测二维标定表或实际运动学模型。单轴角度范围也不能保证多杆组合一定可达或不会碰撞。

过滤从上次实际输出的指令开始，避免输入丢失或切换模式后还因滤波累积而继续向外运动。它限制指令速度，但不保证电机真实速度，也没有加速度/加加速度限制或位置闭环。

## 标定文件

初版采用标准库可读取的 CSV，便于三人填写，也不需要 JSON 第三方库；后续剧本仍可以用 JSON，格式互不影响。CSV 为不带引号的简单格式，第一行有效内容必须为固定表头，允许空行和 `#` 注释。

| 字段 | 单位/作用 |
| --- | --- |
| `axis_id` | 队员一提供的唯一轴名，输出顺序与 CSV 行顺序一致 |
| `rod` | 五个固定杆名之一，见示例文件 |
| `neutral_deg` | 该轴中立角度 |
| `min_deg`、`max_deg` | 已验证的机械安全角度边界 |
| `gain_x_deg`、`gain_y_deg` | 杆目标增加 1 单位时，该轴目标角度的变化 |
| `max_speed_deg_s` | 允许的指令变化速度，必须大于 0 |
| `smoothing_tau_s` | 平滑时间常数，0 禁用平滑；越大响应越缓慢 |

填表步骤：让队员一确认实际轴数和轴名；在独立受控调试中确认中立位置、安全范围和方向；在中立附近分别小幅改变两个杆目标并测量对应角度；由这些测量计算增益；低速验证后再扩大动作幅度。非对称活动范围可能导致一侧较早饱和，不能靠修改安全边界掩盖。

读取器拒绝未知杆名、重复轴名、列数错误、非有限数、反向限位、中立角度超界、非正速度和负时间常数。

## 怎么接入总控程序

最小调用示例：

```cpp
#include "shadow/calibration_csv.hpp"
#include "shadow/motion_mapper.hpp"

auto axes = shadow::load_calibration_csv("config/calibration.simulation.csv");
std::vector<double> initial_commands;
for (const auto& axis : axes) initial_commands.push_back(axis.neutral_deg);
// 上面只适用于本例的模拟初始化。真实系统需传入已归位/初始化后的当前指令。
shadow::MotionMapper mapper(axes, initial_commands);

shadow::ShadowPose pose;
pose.at(shadow::RodId::WusongRight) = {0.5, 0.2, true};
mapper.submit_pose(pose, 0.0);       // 新姿态到达一次，就提交一次
auto commands = mapper.step(0.02);  // 20 ms 后更新控制指令
// 将 commands[i].axis_id 与 commands[i].angle_deg 交给队员一的后端。
```

构造函数必须显式提供每轴初始指令。库不知道电机上电后的真实位置：如果尚未归位，不能简单假设电机已经在中立角度。真实系统先完成队员一提供的初始化/归位流程，再用其确认的当前指令初始化此模块；有位置反馈时还应校验指令与实测状态。

实时循环建议由一个控制线程执行：

1. 使用 `std::chrono::steady_clock`，相对同一起点换算秒数。
2. 取当前模式**新到达**的姿态帧，使用本地接收时间调用 `submit_pose`。不要每轮重复提交缓存旧帧，否则旧数据会被误判为新输入。
3. 无论是否收到新帧，都持续调用 `step`，例如每 20 ms 一次。三种输入可以有不同采样率。
4. 整组将 `angle_deg` 发给电机后端。不要发尚未限速的 `limited_target_deg`。
5. 切模式调用 `clear_inputs`，清理旧模式队列，再提交新模式帧；触控/体感中的老虎待机目标也需要持续生成或允许其超时回中。

默认新输入中断后 0.30 秒内沿用最后有效杆目标；超时后限速回中。每根杆分别计时，不会因为左手持续更新而让已经丢失的右手永远保持有效。实际保持时长通过 `MapperOptions.input_hold_s` 设置。

默认一次控制更新最多允许 0.05 秒的运动量，因此线程停顿数秒也不会一次跳到很远的目标。输入是否超时仍按真实单调时间判断。时间倒退或非有限时间会抛出异常。

`clear_inputs` 只是软件层平缓停靠，不是急停。若整个 Linux 程序崩溃/卡住，`step` 不会执行，软件回中也不会发生；真正的超时保护/失能策略需由队员一在控制后端或硬件中实现。

## 放到 XCZU4EV/PetaLinux 时

本模块运行在 PS 的 Linux 上，不需要转换为 PL 逻辑。队员一把目标角度转换为 PWM 或其后端所需参数。

拿到实际板卡的 PetaLinux SDK 和 sysroot 后，使用该 SDK 的交叉编译环境和 CMake 工具链构建；依赖必须来自目标系统。也可在 PetaLinux 应用 recipe 中用 CMake 构建本库和总控应用。不要把电脑上的 x86/Windows 可执行文件直接当作板上程序。

项目现已在映射核心外补充剧本时间轴、音频后端、关节点重定向、本机进程通信和总控程序，入口请看项目根目录 README。FOLLOW 九点由 Python 薄适配层接入，核心仍是 C++17。下游默认导出 CSV，也可用 `--motor-format jsonl` 导出一周期一组的最终角度；格式见 [电机交接协议](hardware_motor_protocol.md)。真实电机后端、实物标定和 ARM64 上板由硬件队友接入后联调。

总控在剧本暂停时调用 `hold(now_s)`，保持上次已输出的角度并推进控制时钟；恢复时继续限速跟踪。这与输入丢失后自动回中是两个明确的操作。

## 0.1 版本的历史验证记录

2026-09-22 在当前 Windows 电脑上使用 GCC 8.3.0、CMake 3.25.0 和 Ninja 1.13.1 完成 Debug 构建，无编译警告。直接运行 `mapper_tests.exe`，19/19 组测试通过，其中长轨迹测试包含 3000 次控制更新。当前这份 CMake 安装没有附带 `ctest.exe`，因此没有声称在本机执行了 CTest；标准 Ubuntu CMake 安装可使用上面的 `ctest` 命令。

`mapper_demo.exe` 已生成 `build/demo_output.csv`：401 个模拟时刻、10 个示例轴，共 4010 行输出；越界输入记录被标记，停止输入后进入回中状态，8 秒时全部示例轴的输出在打印精度内回到 90 度。这里的 90 度只属于模拟配置。
