# 采集 GUI → TCP → 板端：外部驱动接入

**v0.4 更新：** 用户已改为从观众侧拍摄，真实配置使用 `reference_view: front`；`rear` 仍兼容旧数据。新增 `board_server.py` 服务框架、`board_adapter_template.py` 实物驱动接口模板和 `fit_local.py` 离线局部拟合。完整安装交接流程见 [机械队友使用说明](../../docs/mechanical_handoff.md)。

`shadow_capture --backend external` 通过电脑上的 JSON 请求/ACK 文件与 `tcp_bridge.py` 对接，桥接将请求发送给板端 TCP 服务。GUI 负责摄像头、人工标注和采集记录；板端服务负责验证命令并调用实际驱动。

已确认本项目有 Zynq UltraScale+ 板，机械结构基本装好。PC 桥接和板端接收服务框架已提供；实际 AXI/PL 电机驱动和固件需机械队友接入，尚未在此处实物验证。具体板卡料号、驱动 API、寄存器、PWM/STEP 参数及电气接线需按本项目实物确认。

## 接入前需要确认

| 项目 | 必须提供的信息 |
| --- | --- |
| 轴表 | 每个轴的唯一 `axis_id`、所属杆、实物通道和正方向 |
| 指令单位 | 角度、脉宽、计数或实际驱动使用的单位；两滑台的单位独立填写 |
| 安全范围 | 每个受控轴和可控滑台的实际上下限、每条指令最大变化量 `max_step`；真实驱动独立校验 |
| 初始状态 | 初始化/归位后最后提交的指令；固定机构条件用 `fixed_assumption` 并说明来源 |
| 实际反馈 | 是否有传感器、反馈字段单位和来源；没有反馈时保留 `null` |
| ACK 阶段 | 接收、驱动调用成功、寄存器写入或整组提交；如实描述最远能确认的阶段 |
| 失败和停止 | 超时、断连、拒绝指令、部分更新时的动作，以及独立看门狗和实际急停方式 |

五根杆标识为 `wusong_neck`、`wusong_left`、`wusong_right`、`tiger_head`、`tiger_tail`。左右手按角色自身命名，虎头杆的实物固定点在耳朵处。一根杆可能对应多个轴，不能假定五个或十个电机。

真实配置必须使用实物确认的数据，并设置 `simulation_only: false`。演示配置的 `-1..1` 是无量纲软件数据，`unit: "demo"`，禁止直接用它驱动实际电机。

## 配置格式 v1

软件 v0.2 的配置仍为 `version: 1`。配置是一个 JSON 对象，真实数值需要由驱动与实测确定，不能仅改演示文件的单位名称和模拟范围。

| 字段 | 类型与约定 |
| --- | --- |
| `version` | 整数 `1` |
| `simulation_only` | 布尔值；演示配置为 `true`，外部模式要求真实配置 |
| `stage` | `{ "width_mm": 有效宽度, "height_mm": 有效高度 }`，两者为正数 |
| `reference_view` | `front` 为观众视角、`rear` 为幕后视角；均为各自所见幕布左下原点，x 向右、y 向上。本次使用 `front` |
| `reference_points_mm` | 可选，四个 `[x_mm,y_mm]`；默认左下、右下、右上、左上四角 |
| `axes` | 完整的受控轴数组，每轴为下表结构 |
| `slides` | 两个滑台的状态与可选控制配置，每项为下表结构 |
| `points` | 可选采样计划，每项为 `{ "id": 点标识, "rod": 杆标识, "axes": { 全部轴ID: 目标值 } }` |

| `axes` 每项 | 含义 |
| --- | --- |
| `id`、`rod`、`unit` | 唯一轴 ID、五种合法杆之一、真实指令单位 |
| `min`、`max` | 已确认的安全上下限 |
| `initial` | 配置初始指令，不能作为实物当前位置证明 |
| `jog_step` | GUI 每次点动的变化量 |
| `max_step` | 从最后采用指令到下一条指令的最大变化量 |

| `slides` 每项 | 含义 |
| --- | --- |
| `id`、`unit`、`value` | 唯一滑台 ID、单位、值 |
| `state_kind` | `commanded`：驱动最后指令；`measured`：真实反馈；`fixed_assumption`：固定条件假设 |
| `assumption` | `fixed_assumption` 时必填非空说明，其他状态可省略 |
| `controllable` | 可选布尔值，默认 `false`；为 `true` 时 GUI 可以下发该滑台目标 |
| `min`、`max`、`jog_step`、`max_step` | 可控滑台必填：有限数、`min < max`、初值在范围内、`0 < jog_step <= max_step` |

可控滑台的状态类型只能为 `commanded` 或 `measured`，不能把固定假设作为受控滑台当前状态。范围与步长属于配置，不写入传输状态。`controllable: false` 的滑台只记录条件，不发送运动。

`points` 里的每个点必须给出全部云台轴目标，不能只写当前杆的轴；可省略 `points` 或使用空数组进行手动采集。当前计划不定义滑台目标，执行计划时保留最后采用的滑台值。GUI 校验限位和单次变化量，驱动还应独立校验。不同滑台条件会改变局部映射，调整后需重新确认采集条件。

## 运行方式

以下命令在 Ubuntu 的工程根目录运行。板端 TCP 服务和真实运动驱动验证成功后，先启动 GUI：

```bash
./build-capture/shadow_capture \
  --backend external \
  --config /home/你的用户名/capture.real.json \
  --exchange runtime/bridge \
  --camera 0 \
  --session capture-sessions/real-001
```

每次采集使用一个新会话目录。配置与交换目录属于不同用途：配置描述轴和单位等约定，交换目录承载实时请求/ACK，会话目录保存图片和采样证据。

GUI 显示会话 ID 并创建交换子目录后，在第二个 Ubuntu 终端进入同一工程根目录。把下面的会话 ID 和板端 IP 占位文本替换为真实值：

```bash
python3 integrations/calibration/tcp_bridge.py \
  --session-dir runtime/bridge/GUI显示的session_id \
  --host 板端IP \
  --port 7000 \
  --timeout 4
```

桥接使用 Python 3 标准库，不需安装额外 Python 包。`7000` 是本项目新协议的示例端口，不是板卡已有固件的默认端口；必须与板端服务监听端口一致。启动桥接后，再在 GUI 点击同步。

桥接每次发一条 UTF-8 JSON 并追加换行，板端服务返回一条 JSON ACK 加换行；应答的 `session_id`、`seq` 和 `version` 必须匹配。PC 桥接忽略启动前已有请求，必须完成一次新同步后才允许转发目标，且不会自动重试运动。桥接重启后也需从 GUI 新发同步请求。

`--ack-timeout-ms` 设置等待应答的时长，默认 `5000` 毫秒。首次目标请求之前，操作者先在 GUI 同步当前驱动状态；超时或故障后也必须重新同步。

## 文件交换与 JSON 协议 v1 / v2

没有可控滑台时，请求和 ACK 使用 `version: 1`，请求不含 `slides`。任一滑台配置为可控时，使用 `version: 2`，请求包含全部滑台状态。配置版本、传输版本和样本版本彼此独立；`metadata.json` 的 `request_protocol_version` 记录本会话采用的传输版本。

GUI 在 `<exchange>/<session_id>/requests/` 中写请求，适配进程在同会话的 `acks/` 中写对应应答：

```text
<exchange>/
  <session_id>/
    requests/request_000001.json
    acks/ack_000001.json
```

文件名中的序号与 JSON 的 `seq` 一致，至少补零到六位。GUI 一次等待一条请求，周期检查当前 ACK；ACK 大于 1 MiB 会被拒绝。适配进程只处理完整的最终请求文件，按 `(session_id, seq)` 去重，重复请求不得导致重复运动。

请求字段：

| 字段 | 类型与约定 |
| --- | --- |
| `version` | 按配置为整数 `1` 或 `2` |
| `type` | `capture_sync` 或 `capture_target` |
| `session_id` | 当前会话标识，应答必须原样匹配 |
| `seq` | 本会话递增请求序号，应答必须匹配 |
| `axes` | 全部受控轴，元素为 `{ "axis_id": ID, "value": 指令值, "unit": 单位 }` |
| `slides` | 仅 v2：全部滑台，每项含 `id`、`unit`、`value`、`state_kind`、`controllable` 和必要的 `assumption`；不含范围/步长 |

`capture_sync` **只报告当前状态，不得执行运动**。它的轴和滑台字段明确本次状态集合，服务应返回自己最后采用的真实指令/已知状态，不能把请求初始值写进驱动。`capture_target` 才是目标请求，GUI 只在同步成功后允许发送。v2 中只有 `controllable: true` 的滑台项才是可执行的目标；其余项仅记录条件。

成功 ACK 字段：

| 字段 | 类型与约定 |
| --- | --- |
| `version` | 与请求匹配的整数 `1` 或 `2` |
| `type` | 字符串 `capture_ack` |
| `session_id`、`seq` | 与当前请求一致 |
| `accepted` | 布尔值 `true`；驱动拒绝时用 `false` |
| `adopted` | 驱动最后采用的完整指令数组；元素格式与请求 `axes` 相同 |
| `feedback` | 可省略或为 `null`；有真实反馈时提供非空轴数组，格式与 `axes` 相同，允许只包含有反馈的已知轴 |
| `slides` | 全部滑台状态，含 `id`、`unit`、`value`、`state_kind`、必要的 `assumption`；可省略 `controllable`，若提供必须与配置一致；不含范围/步长 |
| `fault` | 无故障时省略、`null` 或 `false`；有故障时提供故障内容，GUI 拒绝本次采样 |

板端服务应先完整读取并校验目标请求，确认预期的轴/滑台集合、唯一 ID、单位、有限数、限位和最大变化量，再执行实际更新。不能按数组下标猜测驱动通道。ACK 的 `adopted` 必须含全部轴，`slides` 必须含全部滑台；反馈可只含有反馈的轴，所有 ID 和单位均须与配置匹配。驱动最终采用值可以与请求不同，但必须处于配置范围内；样本采用 ACK 中的最终状态，真实轴反馈单独保存。

GUI 用原子写入生成请求文件。适配进程应先将完整 ACK 写入同目录下的临时文件，再在同一文件系统内改名为 `ack_000001.json` 等最终文件；不要直接向最终文件写入半截 JSON。迟到或标识不匹配的 ACK 不得作为当前采样点的应答。

驱动 ACK 的语义必须与真实接口一致。只写寄存器的服务只能确认寄存器写入或最后提交的指令；它不能把请求值回填为实际位置，也不能自行声称云台已经到位。没有实际反馈时，反馈字段省略或为 `null`，样本保持 `null`。只有真实位置传感器数据才写 `feedback`；滑台也按实际来源标记状态类型。

超时不证明命令没有执行，不能据此自动重发运动。GUI 会锁定后续目标请求；适配进程应结合自己的故障状态和最后提交值处理，操作者确认后重新同步。硬件的执行、停止和看门狗不依赖 GUI 轮询计时。

## GUI 与驱动的责任

GUI 在成功 ACK 后等待操作者确认机构停稳，再冻结新帧、接受点击并保存样本。驱动 ACK 与人工确认是两个不同事实：前者证明命令提交阶段，后者记录操作者观察。人工确认不是传感器测量。

任何新的运动指令都会使现有停稳确认、冻结和标注失效，包括其他杆运动。驱动如果在 GUI 之外改变机构或滑台状态，也必须让操作者知道，重新同步、确认并采集；不能继续用旧冻结画面配新指令。

暂停只停止 GUI 安排后续采样点。独立看门狗、使能、实物急停、断连处理和失联后的保持/回中/失能动作由真实驱动或硬件实现。GUI 进程崩溃后不能继续执行软件检查。

真实点动工具可用后，可用 `--backend manual_unconfirmed` 配真实摄像头，先在该工具中实际操作硬件，再手录最后提交的轴指令和滑台值。GUI 不发真实命令，`confirmed: false`。可控滑台按 `commanded` 记录手录命令，仅记录的固定滑台按 `fixed_assumption` 保留人工录入说明。手录仍检查上下限，单次运动步长由实际点动工具负责；采集程序不会用发令步长阻止已执行值的登记。

驱动尚未完成时，允许用演示配置和真实相机练习手录，但其 `demo` 值与记录不能作为实物数据。具体命令见 [安装指南](../../docs/capture_setup.md)。

## 保存版本与真值来源

样本 JSONL 仍为 `version: 1`。`state.axes` 是全部最终指令，`state.feedback` 是真实轴反馈或 `null`，`state.slides` 的每项保留 `state_kind` 和 `controllable`。控制范围与步长保存于 `config.snapshot.json`。`state.confirmed` 仅表示后端是否确认状态，不表示机构停稳或实测位置；手录为 `false`，模拟确认也不是硬件确认。

## 与已有映射程序的关系

原有 [电机目标协议](../../docs/hardware_motor_protocol.md) 输出 `angle_deg`，用于演出控制的最终角度指令。本采集边界需要保留实际驱动单位、全机构状态、人工标注和帧证据，属于独立协议。

采集得到的原始 PNG、JSONL、CSV、配置及单应变换元数据用于后续分析。JSONL 是完整元数据的权威记录；不应把这些样本直接改名为映射器的 `calibration.csv`。应先拟合、校验机构模型，再转换成实际映射器能读取的参数。

电脑安装见 [Windows / VirtualBox 安装指南](../../docs/capture_setup.md)，逐点操作见 [中文采集说明](../../docs/capture_gui.md)。
