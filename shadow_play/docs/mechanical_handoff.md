# 机械队友使用说明：观众视角坐标采集交接包 v0.4

日期：2026-10-07。入口程序是 Ubuntu 桌面上的 C++/Qt/OpenCV 程序 `shadow_capture`。USB 摄像头接运行界面的电脑。Zynq UltraScale+ 负责真实驱动，电脑负责发目标、接收最后采用指令、摄像头取点和保存。

## 1. 收到压缩包后先理解当前完成范围

| 内容 | 本包情况 |
| --- | --- |
| 摄像头实时画面、幕布四角标定、网格、点击取点 | 已有，可运行 |
| 观众视角坐标、对应标记和保存元数据 | v0.4 已补齐，`reference_view: front` |
| 五根杆的轴参数、两滑轨参数和 XY/原始照片配对保存 | 已有；真实单位和限位需填写 |
| 手录实际驱动指令 | 可先使用，记录为 `manual_unconfirmed` |
| 电脑向板卡发指令并接收 ACK | 已有 TCP 桥接；v0.4 新增板端服务框架 |
| 你这块板子的 PWM/滑轨驱动 | 必须接入实际驱动，不能由示例配置推测 |
| 固定其他机构条件下的单杆双轴离线拟合 | v0.4 提供检查工具与交叉验证报告 |
| 全机构联动映射、轨迹执行、实物到位验收 | 需采集实物数据后继续联调；本次拟合 JSON 尚未接入旧演出映射器 |
| 自动识别连接点、自动判断停稳 | 本版没有；使用人工点击和停稳确认 |

交付的是源码包，不是 Windows exe、Zynq 镜像或已验证的电机固件。电脑 GUI 在电脑 Ubuntu 编译；板端服务在 Zynq 的 Linux/PetaLinux 运行。Python 文件是通信与离线分析辅助，主体界面仍是 C++。

## 2. 实物安装与坐标约定

框架外尺寸 800×500×500 mm，**有效幕布宽高要另测**。武松三根杆控制脖子/身体、左手、右手，三云台共柱；老虎两根杆控制耳朵处/头、尾巴，两云台共另一柱。武松轨名义长度 600 mm、虎轨 500 mm，不能将轨长直接当可用行程。

摄像头放观众侧，镜头朝幕布，尽量正对幕布中心，固定位置，完整看见有效区域四角。LED、幕布、相机曝光和皮影离幕距离尽量与演出时一致。

**本次坐标统一使用观众视角：观众看到的幕布左下角为原点，X 向右、Y 向上，单位 mm。** 点击四角顺序也是画面中的左下、右下、右上、左上。软件没有额外镜像画面。用幕布左侧的可见标记检查相机画面确实未镜像。

观众相机看到的是透过幕布呈现的形象/投影。先检查五个连接点是否真的可辨认：看不清机械接点时，选与接点有确定关系、能在观众画面辨认的标记，并在采集备注另存对应说明；不要随意点击附近轮廓当作真实接点。偏移标记随角色转动时，不能简单减一个固定 XY 偏移。

前视角测到的是幕面上的投影坐标。皮影离幕较远时，它不一定等于木杆端点在三维空间的物理坐标。本项目可以以观众看到的幕面位置为控制目标，但要保持这一定义，不能混入幕后相机数据。

旧数据如为 `rear`，同一幕面点的理论换算是 `x_front = 有效宽度 - x_rear`、`y_front = y_rear`。本工具不会自动修改旧剧本或旧映射。相机搬动、画面镜像、分辨率改变、有效幕布改变后重新做四角标定。角色左右手名称始终按角色自身，不能随相机视角改名；双方不换边的限制按新视角重新核对。

## 3. 在机械队友电脑 Ubuntu 安装与编译

Windows + VirtualBox 可以使用；以下命令全部在 Ubuntu 终端执行。先把压缩包复制到 Ubuntu 主目录。建议解压到 Ubuntu 自己的主目录，再编译，避免共享目录权限和旧 CMake 缓存问题。

```bash
sudo apt update
sudo apt install build-essential cmake pkg-config qtbase5-dev libopencv-dev fonts-noto-cjk unzip v4l-utils usbutils python3 python3-numpy
mkdir -p ~/shadow-handoff-v0.4
unzip -n ~/shadow-capture-handoff-v0.4.zip -d ~/shadow-handoff-v0.4
cd ~/shadow-handoff-v0.4/shadow_play
cmake -S . -B build-capture -DSHADOW_BUILD_CAPTURE=ON -DSHADOW_ENABLE_ALSA=OFF -DBUILD_TESTING=ON
cmake --build build-capture --parallel 2
```

运行采集相关软件测试（兼容 Ubuntu 20.04 的 CMake）：

```bash
cd ~/shadow-handoff-v0.4/shadow_play/build-capture
ctest -R capture_ --output-on-failure
cd ..
```

测试使用合成画面和模拟驱动，测试通过不等于实物已验证。仅运行电脑 GUI 不需要安装 Vivado 的 UltraScale+ 器件包；机械队友实现/修改 PL 时才使用匹配板卡的 Vivado 工程，更新板卡系统时才用 PetaLinux。GUI 编译使用 CMake 和 GCC。

USB 摄像头先在 Windows 确认可用并关闭相机应用，再在 VirtualBox 运行窗口底部 USB 图标选择摄像头，转交 Ubuntu。如果需要改 USB 控制器，应先正常关闭虚拟机。随后检查：

```bash
lsusb
v4l2-ctl --list-devices
```

找到实际视频采集节点 `/dev/videoN`，下面命令的 `--camera 0` 按实际编号改。Zynq 摄像头接口不参与本次采集。

先练习界面，不接电机：

```bash
./build-capture/shadow_capture --demo --reference-view front --config config/capture.demo.json --session capture-sessions/practice-001
```

摄像头练习和桌面快捷方式：

```bash
python3 integrations/calibration/capture_launcher.py --install-shortcuts
```

桌面入口现在默认观众视角。首次摄像头入口填写相机编号和有效幕布尺寸；它仍是 `demo` 指令练习，**正式采集用下方真实配置命令**。桌面图标需“允许启动”时右键操作。

## 4. 先把真实驱动信息填好

先完成 [硬件参数填写表](hardware_capture_checklist.md)。板卡具体型号、舵机 PWM/总线类型、转角范围、供电电平、通道、时钟、AXI 寄存器地址、滑轨驱动形式目前未提供，不能从框架尺寸或商品照片推算。

生成待填配置：

```bash
python3 integrations/calibration/prepare_real_config.py config/capture.real.json
```

文件内所有 `null` 和 `UNCONFIRMED` 都必须按实际填写。保留五根杆 ID；生成的十轴只是按五个双轴云台列出的待核对轴表，可按最终驱动调整。`initial`/滑轨 `value` 是已初始化后的指令参考值，并不让硬件自动移动。`points: []` 先保留，逐次小幅点动。

填写后检查数值格式：

```bash
python3 integrations/calibration/board_server.py --config config/capture.real.json --check-config
```

检查通过只代表配置格式/数值关系正确，通道和物理范围还要实测。每轴需给 `unit`、`min`、`max`、`initial`、`jog_step`、`max_step`。若使用脉宽，应明确如 `us`；若使用角度，写 `deg` 并保证驱动转换定义一致。PWM 周期、极性、计数时钟等固定参数写在硬件填写表和实际驱动中，采集软件不猜测。

滑轨单独确认：若为步进驱动器，常见控制可能是 STEP/DIR 或驱动器总线，不能直接照搬舵机 PWM。回零后可约定位置单位 mm，驱动负责换算步数并执行速度/加速度控制。无位置传感器时记 `state_kind: commanded`。

## 5. 路径 A：先用现有点动工具驱动，界面手录

真实驱动已能动，但 TCP 尚未接好时使用：

```bash
./build-capture/shadow_capture --camera 0 --backend manual_unconfirmed --config config/capture.real.json --session capture-sessions/manual-001
```

1. 在你自己的驱动工具上发一组命令，记录驱动实际采用的全部轴值和两条滑轨值。
2. 在采集界面输入这些值，点击“登记以上命令（未确认）”；首次按界面登记当前状态。
3. 选当前记录的杆，观察所有相关机构停稳，勾选停稳确认。
4. 冻结新画面，点击对应连接点；界面算出 XY。
5. 核对右侧指令及坐标，勾选核对确认，点击保存。

手录模式不会驱动电机，`confirmed: false` 如实标记命令没有通信确认。实际指令变了就重新登记，不能继续保存旧状态。这里手录的是驱动值，XY 是点击后自动计算。

## 6. 路径 B：接上 Zynq，实现发令与指令回传

数据流：

```text
电脑 Ubuntu 采集 GUI（目标指令）
    → requests/*.json
    → 电脑 tcp_bridge.py
    → 网线/LAN TCP
    → Zynq PS Linux board_server.py
    → board_adapter_local.py（机械队友接实际驱动）
    → PS 驱动 / AXI 寄存器或其他已实现接口
    → PL 的舵机 PWM / 滑轨控制信号 → 电机 → 木杆 → 皮影

驱动最后采用的整组指令 → PS 服务 ACK → TCP → 电脑桥接
    → acks/*.json → GUI 右侧显示并保存

USB 摄像头 → 电脑 OpenCV → 冻结照片 → 点击连接点 → 幕面 XY
    → 与同一状态编号的指令一起保存
```

**电脑没有直接测量 PWM 引脚波形。** ACK 是驱动报告的数值。真实波形用示波器/逻辑分析仪核验；`adopted` 是最后提交值，`feedback` 只放传感器测量，无传感器就是 `null`。ACK 成功不等于电机到位。

机械队友需要实现两个 Python 接口，或让这两个接口调用已有 C/C++ 驱动：

```bash
cp integrations/calibration/board_adapter_template.py integrations/calibration/board_adapter_local.py
```

- `create_driver(config)`：连接已经初始化的驱动，不自动发运动。
- `read_state()`：读取完整最后采用指令和滑轨状态，不移动机构；启动后状态未知时必须报错。
- `apply_targets(axes, slides)`：先校验整组，再提交实际驱动；返回实际采用状态，包括量化后的值。部分提交失败时按已验证的停止策略处理、报告故障，不能回填请求伪装成功。

板端需 Python 3；若 PetaLinux 未带 Python 3，队友可在系统配置中加入，或按同一协议实现 C++ 服务。电脑 GUI、Qt、OpenCV、NumPy 不必装到板上。Python 仅处理低速采集请求，PWM 波形由板端实时驱动/PL持续产生。

把 `integrations/calibration/` 与同一份 `config/capture.real.json`、实际驱动拷到板端工程目录。先用板端工具初始化舵机/滑轨、回零并建立真实指令状态，再启动服务。以下 IP 都要替换：

```bash
# 在 Zynq 板端终端，进入板端工程目录后运行
python3 integrations/calibration/board_server.py --config config/capture.real.json --adapter integrations/calibration/board_adapter_local.py --bind 板卡局域网IP --port 7000 --log board-capture.jsonl
```

模板未实现时会明确拒绝启动，不会假装已经驱动。服务一次只接受一个 GUI 会话，单线程串行提交；要求驱动调用有界返回。它不提供硬件急停、位置闭环或独立看门狗，这些由实际驱动实现。通信只放在可信的实验局域网，服务未实现身份认证。

电脑与板卡网口接同一局域网或直连并配置地址。先确认 Ubuntu 内能访问板卡 IP；Windows 能访问不代表虚拟机一定能访问。GUI 发起出站 TCP 连接，VirtualBox 可先保留 NAT 测试，直连路由不通再配置合适网卡/桥接。串口可用于板端控制台；本包自动记录协议走 TCP，不从串口打印中猜指令。

电脑终端 1：

```bash
cd ~/shadow-handoff-v0.4/shadow_play
./build-capture/shadow_capture --camera 0 --backend external --config config/capture.real.json --exchange runtime/bridge --session capture-sessions/real-001
```

终端 2：把下面“界面显示的会话ID”替换成 GUI 顶部显示的 ID：

```bash
cd ~/shadow-handoff-v0.4/shadow_play
python3 integrations/calibration/tcp_bridge.py --session-dir runtime/bridge/界面显示的会话ID --host 板卡局域网IP --port 7000 --timeout 4
```

桥接启动后，在 GUI 点击“读取 / 同步驱动状态”。`capture_sync` 只查询，不能使电机运动。之后在 GUI 设置小幅目标并提交；此阶段 GUI 是唯一发令入口，不同时使用另一工具改动电机。冻结前 GUI 会再同步一次指令，但这不能阻止其他程序随后移动，所以采样期间必须保持独占控制。

协议完整定义见 [采集驱动接口](../integrations/calibration/README.md)。服务缓存同一 `(session_id,seq)` 的结果，重复命令不重复运动；超时不自动重试。超时后先确认机构与驱动状态，再重新同步。板端服务重启后，关闭旧 GUI，使用新的采集会话，不续用旧会话重放命令。

## 7. 每次实际采样按这个顺序

1. 同步/登记初始指令，打开相机；填写表中的电机单位要与界面一致。
2. 点击“设置幕面四个参考点”，依次点击画面左下、右下、右上、左上。用幕布内部已知位置检查坐标误差；若边缘明显弯曲，四点校正不能解决镜头畸变，应先调整镜头/距离或补充相机标定。
3. 选择杆：武松身体、左手、右手、虎头、虎尾中的一个。左右手按角色身份。
4. 先固定其他轴和两条滑轨，选本杆两个轴的小范围目标；提交后右侧应显示驱动采用值。
5. 观察停稳，勾选确认，冻结新画面，点击可辨认的对应接点。
6. 核对驱动值、滑轨值、XY 和杆名，确认保存。
7. 改变目标，重复。先测少量点查通道、方向、画面与指令对应，再扩大范围。不要一开始就扫满行程。

建议先做一根杆的 5×5 局部网格，并选择若干位置从不同方向重复到达，用于观察间隙和回差。这只是起步方案，采多少最终取决于可达范围、非线性和独立验证误差。网格是两个轴的指令组合，不要求木杆扫遍幕布每个像素。

两轴单独变化只能检查方向；正式拟合需要两个轴共同变化的二维覆盖。换滑轨位置、改变其他杆姿态后属于新的机构条件，先新建会话采一组。木杆连接在关节上会互相牵制，单杆固定条件的拟合不能直接保证五杆联动效果。

## 8. 文件保存与离线拟合

每次 `--session` 必须是未存在的新目录。文件保存在该目录中，例如：

```text
capture-sessions/real-001/
  samples.jsonl            每条样本完整指令、滑轨、XY、照片路径与状态编号
  samples.csv              方便查看的表格，完整轴/滑轨状态在单元格 JSON 中
  metadata.json            会话来源、视角、协议版本
  config.snapshot.json     本次实际配置快照
  requests.jsonl           GUI 请求记录
  calibration_000001.json  四角、单应变换、相机图像尺寸与视角
  capture_source.json      相机来源
  frames/sample_000001.png 原始照片
```

每次保存记录整组轴指令和两滑轨，不仅是选中杆的两个值。JSONL 是权威记录；CSV 需和同目录元数据一起保留。PNG 是原始相机照片，不是界面截图。

固定其他机构条件的单杆局部拟合：

```bash
python3 integrations/calibration/fit_local.py capture-sessions/real-001 --rod wusong_neck --degree 1 --output fit-results/wusong-neck-linear.json
```

至少 12 个不同双轴指令组合才能做一次线性分析；二次模型用 `--degree 2`，至少 20 组。程序使用“每次留出整组相同指令”的交叉验证，避免重复点同时落入训练和验证造成虚假的好成绩。手录数据在人工核对后另加 `--allow-manual`；模拟数据始终拒绝。

输出包含指令→XY 与 XY→指令的局部模型、各轴指令误差、前向预测毫米误差、重复位置散布、固定条件和原始点。若其他轴、两滑轨或幕面标定变化会拒绝混合拟合。先看预测毫米误差，再用未参与采集的新目标点做低速实物验证，记录实际目标误差。

**这个 JSON 是离线分析结果，`deployment_ready: false`。现有演出 `motion_mapper` 不会直接加载它。** 后续需要根据实物误差决定分区/插值或几何模型，接入统一坐标映射器，再补齐滑轨和五杆联动、限位、轨迹速度与音频同步。不要将拟合 JSON/采集 CSV 改名成旧 `calibration.csv`。

采完把整个会话目录、板端 `board-capture.jsonl`、填写好的参数表、实际驱动代码和拟合报告打包发回。相机位置/光源/杆长/连接点/机械零位发生变化要说明，不能只发一张截图或一个 CSV。

## 9. 机械队友如何配合 Codex

在能访问工程源码和 Ubuntu 构建环境的 Codex 中打开解压后的 `shadow_play`。先把实际 Vivado/驱动工程、原理图、板卡型号和已填写参数表提供给它；需要操作板端时，先由人建立可用的 SSH/串口连接并说明工程路径。Codex 不会仅凭这个压缩包推断接线或自动获得板卡连接。

第一阶段可以直接复制以下任务：

> 阅读 docs/mechanical_handoff.md、docs/hardware_capture_checklist.md 和 integrations/calibration/README.md。先在 Ubuntu 编译运行采集测试，确认观众视角坐标。检查我提供的实际板卡、PL 和电机驱动工程；列出尚缺的通道、单位、PWM 周期/时钟、限位、滑轨回零和停止接口。根据已核实的驱动实现 board_adapter_local.py，填写 capture.real.json。read_state 必须读最后实际采用状态，capture_sync 不能运动，反馈缺失保持 null。先用模拟驱动验证协议，再在我指定的轴、范围、步长和现场看护条件下执行实物点动。不要猜寄存器地址或将 demo 值用作实物指令。

后续分阶段给它任务：

1. 验证一个轴，示波器核验真实输出；再验证另一个轴和滑轨回零/方向/限位。
2. 接通 GUI→桥接→板端→驱动→ACK，检查驱动实际采用值是否保存，测试拒绝/超时/重新同步。
3. 人工停稳并点击记录一根杆的小范围数据。Codex 可按已经核实的计划辅助生成下一组指令；本版每次取点仍由人确认，不能无人值守猜坐标。
4. 读取采样目录运行离线拟合，报告数据覆盖、重复性、验证误差，再安排独立实物验证。
5. 在数据证据支持后，实现多杆/滑轨协调映射，接入三种输入，最后合成动作和音频。

Codex 项目说明可使用 `AGENTS.md`；应写实际可执行的构建命令、板卡事实和调试范围。参考 [OpenAI 官方项目说明文档](https://learn.chatgpt.com/docs/agent-configuration/agents-md)。本包通过上述可复制任务传递上下文，不依赖本聊天的历史。

## 10. 压缩包交接和后续版本

本次直接发 `shadow-capture-handoff-v0.4.zip` 即可。让队友从本版继续，不覆盖到旧构建目录。源码在他那里改完后，把修改过的源文件和版本说明一并发回，避免双方各改一份后无法追踪。

以后团队使用 GitHub 时放解压后的源码目录，构建目录、runtime 和原始采集照片已由 `.gitignore` 排除；实物数据单独打包保存。正式驱动源码和已核实参数应纳入团队版本记录，账号密码不写进源码。
