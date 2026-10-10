# Windows + VirtualBox Ubuntu：从安装到标定采集

本指南保留电脑端 `shadow_capture` v0.2 的安装步骤。**本次 v0.4 交接请优先阅读 [机械队友使用说明](mechanical_handoff.md)，摄像头已改为观众视角，使用 `front` 配置。** 窗口在 VirtualBox 的 Ubuntu 桌面中运行；USB UVC 摄像头直接插在这台 Windows 电脑上，再转交给 Ubuntu。界面显示幕面、XY 坐标和右侧电机/滑台操作区。

目前已确认你有 Zynq UltraScale+ 板，但云台和两个滑台还没有能使它们运动的驱动。本软件可以先完成演示、电脑摄像头预览、幕面参考和人工取点。真正运动还需要本项目自己的板端驱动、通信服务和电气接线；其他比赛的板卡资料、队友代码和器件型号不能直接套用。

## 第 1 步：明确每个环境安装什么

| 环境 | 软件 | 何时需要 |
| --- | --- | --- |
| Windows | VirtualBox | 运行已有 Ubuntu 虚拟机；已有可用安装就继续使用 |
| Windows | VS Code | 可选编辑器；已有安装可继续用，不是运行 GUI 的必要条件 |
| Windows | VirtualBox Extension Pack | 使用专门的“设备 → Webcams”功能时需要；见第 6 步 |
| Windows | Vivado 与正确器件支持 | 你自行编译 Zynq 的 FPGA/PL 设计时需要；版本按板卡工程确认 |
| Windows | 厂商 JTAG/USB 驱动 | 所用下载线或 USB 控制器要求时，按其官方说明安装 |
| Windows 或所支持开发环境 | Vitis | 可选：选择裸机 PS 控制应用路线时使用；Linux 服务可按已有 SDK 构建，不要求另装 Vitis |
| Ubuntu 虚拟机 | C++ 编译器、CMake、Qt5、OpenCV、中文字体等 | 构建和运行本采集界面；第 2 步一次安装 |
| 支持的 Linux 构建环境 | PetaLinux | 自行构建或修改板端 Linux 镜像时需要；版本须匹配板卡工程 |

电脑上的 Qt5/OpenCV GUI 构建不依赖 Vivado 或 PetaLinux。若已有正确的板端镜像及控制固件，只运行采集界面也无需重新构建它们；你当前尚未完成运动驱动，因此仍需安排板端开发。

SSH 和串口工具按使用方式选择：Ubuntu 若需 SSH 登录板端，可安装 `openssh-client`；若使用串口控制台，可安装 `minicom`。Windows 也可选用 PuTTY。它们不需要全部安装；串口端口、波特率和登录方式按板卡厂家 BSP 说明，PC GUI 编译不依赖这些工具。

## 第 2 步：在 Ubuntu 安装界面依赖

启动 VirtualBox Ubuntu，进入桌面，打开 Ubuntu 终端。以下命令都在这个终端执行：

```bash
sudo apt update
sudo apt install build-essential cmake pkg-config qtbase5-dev libopencv-dev fonts-noto-cjk unzip v4l-utils usbutils python3
```

输入的是 Ubuntu 登录密码；输入密码时终端不显示字符是正常的。每条命令成功后再继续。依赖作用：

| 包 | 用途 |
| --- | --- |
| `build-essential`、`cmake`、`pkg-config` | 编译 C++ 和查找库 |
| `qtbase5-dev` | Qt5 中文窗口、按钮和输入框 |
| `libopencv-dev` | 摄像头、图像和幕面透视转换 |
| `fonts-noto-cjk` | 中文字体，避免界面文字显示成方框 |
| `unzip` | 解压源码包 |
| `v4l-utils` | 查看 Ubuntu 摄像头设备 |
| `python3` | 运行包内 PC TCP 桥接脚本；安装它不会自动产生电机驱动 |

检查工具是否可用：

```bash
cmake --version
g++ --version
pkg-config --modversion opencv4
qmake -query QT_VERSION
```

Windows、WSL 和 VirtualBox Ubuntu 的软件安装彼此独立。Windows 安装了 VS Code 或另一套 Ubuntu 安装过 CMake，都不代表当前虚拟机已经有这些依赖。

## 第 3 步：把源码包复制进 Ubuntu

把 `shadow-capture-v0.2.zip` 从 Windows 复制到 Ubuntu 的主目录。可使用已经配置好的共享文件夹、U 盘或文件拖放。VirtualBox 文件拖放需要 Guest Additions 和对应设置；这是文件传输功能，与摄像头转交不是同一项设置。[Oracle 文件拖放说明](https://docs.oracle.com/en/virtualization/virtualbox/7.1/user/BasicConcepts.html)

确认 Ubuntu 文件管理器的主目录中能看到 ZIP，再执行：

```bash
cd ~
mkdir -p ~/shadow-capture-v0.2
unzip -n ~/shadow-capture-v0.2.zip -d ~/shadow-capture-v0.2
cd ~/shadow-capture-v0.2/shadow_play
pwd
ls
```

包内根目录为 `shadow_play`。`ls` 应能看到 `CMakeLists.txt`、`src`、`include`、`config`、`docs`、`third_party` 等。ZIP 文件名若不同，就使用你实际收到的名称。

`~/shadow-capture-v0.2` 是解压容器。如果它已经装过别的版本，换一个空容器目录并同步修改 `-d` 与 `cd` 路径，避免旧文件混入新版本。`/mnt/d/ZYNQ` 是 WSL 的路径示例，不能当成 VirtualBox 中自动存在的路径。

## 第 4 步：编译采集程序

当前目录必须是包含 `CMakeLists.txt` 的工程根目录：

```bash
cmake -S . -B build-capture \
  -DSHADOW_BUILD_CAPTURE=ON \
  -DSHADOW_ENABLE_ALSA=OFF \
  -DBUILD_TESTING=OFF
cmake --build build-capture --target shadow_capture --parallel 2
```

第一条配置工程，第二条才编译。成功后检查：

```bash
./build-capture/shadow_capture --help
```

构建失败时先看第一条实际错误；可执行文件尚未生成时，继续运行启动命令只会得到“没有那个文件或目录”。不能复用从 Windows 或 WSL 复制来的旧构建缓存；换一个新构建目录并一致更改后续路径。

## 第 5 步：不接硬件，先练习演示

首次编译成功后，可以按 [Ubuntu 双击启动说明](capture_launcher.md) 安装桌面入口。入口记住相机编号和幕布尺寸，每次自动使用新的采集目录，以后无需重复长启动命令。v0.2 旧包需要先加入该说明所列的启动补丁。

在工程根目录执行：

```bash
./build-capture/shadow_capture \
  --demo \
  --config config/capture.demo.json \
  --session capture-sessions/demo-001
```

`--session` 后面的会话目录必须尚不存在，程序会创建它。**不要提前 `mkdir capture-sessions/demo-001`。**重复运行可使用 `demo-002`、`demo-003`；既有结果不会被覆盖。

演示的电机和滑台指令使用无量纲单位 `demo`，只在软件中改变模拟状态，不会使实物运动。演示幕面尺寸也仅是示意值。

依次练习：

1. 点击“设置幕面四个参考点”，在原始图上按左下、右下、右上、左上点选四角。
2. 四点完成后，界面显示透视展开后的有效幕面，左下为 `(0,0)`，向右是 X，向上是 Y，单位 mm。右侧保留连接点选择、轴/滑台字段和采样操作。
3. 选择一根杆，试用其轴旁的“− / ＋”，或提交本组模拟目标。
4. 勾选人工停稳确认，点击冻结新画面的按钮。
5. 在幕面图中点击当前杆的连接点，核对右侧指令与 XY，勾选“我已核对右侧指令及取点坐标”，再点击“确认并记录本组数据和照片”。
6. 取消取点后可重拍；默认保存后需显式执行下一采样组。熟悉流程后再使用“保存后自动执行下一组”。

窗口里的透视展开只用于观察和点选；保存的 PNG 仍是完整原始帧，点击坐标会反算回原图像素。完整操作与状态解释见 [采集界面说明](capture_gui.md)。

## 第 6 步：把电脑 USB 摄像头交给 Ubuntu

这里使用电脑的 USB UVC 摄像头，不要求经过 Zynq 摄像头接口。先在 Windows 相机应用中确认它有画面，然后关闭相机应用、视频会议和其他占用相机的软件。

推荐先使用通用 USB 转交：

1. 正常关闭 Ubuntu 虚拟机。
2. 在 VirtualBox 管理器选中该虚拟机，进入“设置 → USB”，启用 USB 控制器。当前 Oracle 文档通常推荐 xHCI；按你的 VirtualBox 版本和设备支持配置。
3. 启动 Ubuntu，在虚拟机窗口的“设备 → USB”菜单中选择这只摄像头。
4. 需要以后自动连接时，可在 USB 设置中为这只摄像头添加设备过滤器。只选择目标设备。

USB 转交后，该设备由虚拟机使用。上述控制器、过滤器和菜单路径来自 [Oracle USB 设置说明](https://docs.oracle.com/en/virtualization/virtualbox/7.1/user/BasicConcepts.html)。

若改用专门的“设备 → Webcams”途径，Oracle 文档明确说明 Webcam Passthrough 模块属于单独安装的 Extension Pack；按当前 VirtualBox 版本的扩展包说明安装后再选择相机。通用 USB 转交与这项 Webcam 功能不要重复绑定同一设备。[Oracle Webcam Passthrough 说明](https://docs.oracle.com/en/virtualization/virtualbox/7.1/user/AdvancedTopics.html)

回到 Ubuntu 终端检查：

```bash
lsusb
v4l2-ctl --list-devices
ls -l /dev/video*
```

如果看不到相机，先解决转交问题，再启动 GUI。输出中找到实际视频设备，如 `/dev/video0`；有的相机还会列出元数据设备，不能只按设备数量猜相机编号。

使用真实摄像头画面、软件模拟指令：

```bash
./build-capture/shadow_capture \
  --backend simulation \
  --camera 0 \
  --config config/capture.demo.json \
  --session capture-sessions/camera-practice-001
```

`--camera 0` 对应程序打开的视频设备编号，必要时换实际编号。`--demo`、`--camera`、`--image` 必须且只能选一种来源，不能同时传 `--demo --camera 0`。

## 第 7 步：用真实画面练习手录和取点

驱动尚未完成时，可以先练习手录模式：

```bash
./build-capture/shadow_capture \
  --backend manual_unconfirmed \
  --camera 0 \
  --config config/capture.demo.json \
  --session capture-sessions/manual-practice-001
```

这条命令仍用演示的 `demo` 单位，适合练习相机、登记、冻结、点击和保存；不控制电机，所得记录不能当成真实机构指令样本。手录模式标记 `manual_unconfirmed`，没有驱动确认和实际位置反馈。

开始实际机构采集前，先根据本项目的真实驱动制作 `capture.real.json`：填入完整轴表、实际单位、已确认的上下限、步长、两个滑台及有效幕面毫米尺寸，设置 `simulation_only: false`。不要只把演示文件中的标志改成 `false`，就把 `demo` 值当成 PWM。

真实驱动或独立控制工具能够执行后，再用真实配置手录其最终采用值：

```bash
./build-capture/shadow_capture \
  --backend manual_unconfirmed \
  --camera 0 \
  --config /home/你的用户名/capture.real.json \
  --session capture-sessions/manual-real-001
```

这时仍需实际控制工具执行动作，再在本界面登记全部轴和滑台状态。当前尚无运动驱动，不能仅凭手录界面的数值变化认定云台或滑台已经移动。

## 第 8 步：补齐 Zynq 控制链，才会有真实运动

本项目采用以下建议连接方式。包内提供 PC TCP 桥接脚本；板端通信服务和运动驱动仍需开发：

```text
PC 上的 Ubuntu GUI
    ↓ JSON 文件请求 / ACK
PC TCP 桥接进程（包内 tcp_bridge.py）
    ↓ 网络
Zynq 板 PS 接收服务（需要实现）
    ↓ 已定义的 AXI 寄存器或驱动接口
PL 云台 / 滑台控制逻辑（需要实现）
    ↓ 与电机匹配的控制信号
舵机输入或电机驱动器 → 实物云台和两个滑台

PC USB 摄像头 → Ubuntu GUI（直接取幕布图像）
```

电脑发送的是目标命令。实际 PWM、STEP/DIR 或总线命令由对应控制板和驱动系统产生；文件交换目录本身不提供网络传输、电机电源或驱动波形。

电脑 USB 可承载相机或控制器通信，不能直接代替电机驱动；FPGA 引脚输出控制逻辑信号，不能直接为电机供电。若实际确认五台云台各使用两个 RC 舵机，对应需要十路 PWM；实际轴数、信号类型和接线仍以实物为准。

| 已确认的电机/驱动类型 | 所需控制实现 |
| --- | --- |
| 若云台使用 RC 舵机 | 依据具体舵机规格生成控制脉冲，并确认供电和角度/脉宽关系 |
| 若滑台使用步进电机与 STEP/DIR 驱动器 | 实现脉冲、方向、使能、速度/加速度及回零/限位；需要毫米与步数换算 |
| 若滑台或云台使用总线驱动器 | 按厂商总线协议发送目标并处理驱动反馈、故障与停止 |

实际类型未确认前不能选择其中一种当作既定方案，也不能填写任意 PWM 范围、脉冲频率、寄存器地址或引脚。PL 的逻辑信号还必须与所用电机驱动器的接口、电平及接线匹配。

开始实现时先整理这些信息：完整开发板型号与 FPGA 完整料号、板卡工程版本、云台电机型号与每台轴数、两条滑台电机及驱动器型号、控制接口、供电/接线图、限位与归位方式、有没有实际位置反馈。五根杆不固定为五个或十个电机。

包内 `integrations/calibration/tcp_bridge.py` 读取 GUI 文件请求，将一条 UTF-8 JSON 加换行发往板端 TCP 服务，并将板端返回的匹配 ACK 写回交换目录。板端服务须按 [采集外部协议](../integrations/calibration/README.md) 完成校验和真实驱动提交，再根据真正完成的阶段回复；不能仅回写请求值就声称硬件已经执行。ACK 也不表示电机已经到位。

### 网络实际怎么接

推荐电脑和板卡的 Ethernet 接到同一个路由器，先让板端网卡获得该局域网内的 IP。按厂家 BSP 说明启动板端 Linux，通过厂家规定的串口控制台或已有 SSH 登录查看网卡地址；在**板端终端**可用 `ip addr` 查看 Ethernet 的 IPv4 地址，不能把 Ubuntu 虚拟机自己的地址抄成板端地址。

VirtualBox 的 Ubuntu 可先保留 NAT 网络模式，由 PC 桥接主动连接板端局域网 IP。Oracle 文档说明 NAT 会通过 Windows 主机转发虚拟机发出的连接；这条连接不要求板端反向访问 Ubuntu 服务。[Oracle NAT 说明](https://docs.oracle.com/en/virtualization/virtualbox/7.1/user/networkingdetails.html)

板端 TCP 服务必须监听可从局域网访问的板端地址或所有相应接口，并允许约定端口通过其网络设置。仅监听板端 `127.0.0.1` 时，电脑无法访问。桥接的 `--host` 填实际板端 IP，不能填 Ubuntu 的 `localhost`。板端尚未启动网卡、服务未实现或端口未开放时，先解决这些条件；更改 GUI 数字不会建立这条连接。

## 第 9 步：按板卡工程配置 Vivado / PetaLinux

你自行实现 PL 云台和滑台逻辑时，需要在 Windows 的 Vivado 中安装实际 Zynq UltraScale+ 对应的器件支持，并选择完整目标料号。不能用 Zynq-7020 工程的器件、引脚或寄存器资料替代未知的 UltraScale+ 板。

先核对板卡厂家工程、已有 Vivado、BSP 和 PetaLinux 的版本，再决定补装内容。Vivado 安装器可选择需要的器件族；已安装后也可以通过“Add Design Tools or Devices”补装。操作入口会随版本略有区别。[AMD UG973 安装器件说明](https://docs.amd.com/r/2025.1-English/ug973-vivado-release-notes-install-license/Run-the-Installation-File)，[AMD 补装器件说明](https://docs.amd.com/r/2025.1-English/ug973-vivado-release-notes-install-license/Adding-Additional-Tools-and-Devices)

PetaLinux 用于构建板端嵌入式 Linux，与电脑端 GUI 的 Qt/OpenCV 依赖是两套用途。需要构建板端 Linux 时，按所用版本的受支持 Linux 环境、BSP 和硬件导出文件配置。AMD 的 2025.1 文档明确要求该版 PetaLinux 使用 Vivado 2025.1 导出的设计；这里用它说明版本匹配要求，不是在指定你安装 2025.1。[AMD UG1144 用途说明](https://docs.amd.com/r/2025.1-English/ug1144-petalinux-tools-reference-guide/Introduction)，[AMD 版本与安装要求](https://docs.amd.com/r/2025.1-English/ug1144-petalinux-tools-reference-guide/Installation-Requirements)

本次采集软件包没有未知板卡的 bitstream、板端控制服务或 SD 卡启动镜像，不能把电脑端可执行文件直接当成板端 ARM 程序。

## 第 10 步：真实外部模式的启动条件

完成并验证板端控制链、TCP 接收服务和真实配置后，先在 Ubuntu 终端 A 的工程根目录运行 GUI：

```bash
./build-capture/shadow_capture \
  --backend external \
  --camera 0 \
  --config /home/你的用户名/capture.real.json \
  --exchange runtime/bridge \
  --session capture-sessions/external-real-001
```

GUI 会显示本会话 ID 并建立交换子目录。在终端 B 进入同一个工程根目录，再启动 PC 桥接；把下面的 `GUI显示的session_id` 和 `板端IP` 替换成实际值：

```bash
python3 integrations/calibration/tcp_bridge.py \
  --session-dir runtime/bridge/GUI显示的session_id \
  --host 板端IP \
  --port 7000 \
  --timeout 4
```

`7000` 是本项目新 TCP 协议的示例端口，不是已有板卡固件默认端口。板端服务必须监听双方选定的相同端口，Ubuntu 必须能连通该 IP 和端口。GUI 默认等待 ACK 5 秒，此处桥接请求超时为 4 秒。

桥接启动后，才在 GUI 点击“读取 / 同步驱动状态”。桥接忽略启动前已有的请求，并要求一次新的同步成功后才转发运动目标，避免重放旧运动；失败不自动重试运动。之后从已确认的初始值小幅点动。界面能够为配置为可控的滑台下发目标，但真实动作仍由板端驱动执行。当前板端服务和运动驱动尚未完成，不能仅启动桥接就使电机运动。

采集按“命令被采用 → 人工观察停稳 → 冻结新画面 → 点击连接点 → 核对右侧指令与 XY → 勾选核对 → 确认记录”执行。保存按钮为“确认并记录本组数据和照片”，需先勾选“我已核对右侧指令及取点坐标”。冻结后发生新运动需重新取样。暂停发令只停止安排后续请求，独立看门狗、故障停机和实物急停由控制系统实现。

## 常见问题

| 现象 | 处理 |
| --- | --- |
| `cmake: command not found` | 在当前 VirtualBox Ubuntu 完成第 2 步 |
| 中文显示方框 | 确认 `fonts-noto-cjk` 安装成功，重启 GUI |
| 找不到 ZIP / 工程目录 | 在 Ubuntu 文件管理器确认位置，再修改 `unzip` 和 `cd` 路径 |
| 会话目录已存在 | 换一个新名称，不提前创建该会话目录 |
| Windows 相机有图，Ubuntu 无设备 | 关闭 Windows 相机占用，检查 VirtualBox USB 转交，再查看 `v4l2-ctl --list-devices` |
| 相机打不开 | 核对视频设备编号、设备权限及其他程序占用 |
| 幕面方向或比例错误 | 检查背面视角、四点对应顺序和实际有效尺寸；相机移动后重标 |
| “− / ＋”只改变数字或演示图 | 检查模式；模拟和手录都不会控制实物 |
| 外部 ACK 超时 | 检查适配进程、板端服务和通信；超时后重新同步，不自动重发运动 |
| 保存按钮不可用 | 检查登记/ACK、人工停稳、冻结、点选、“我已核对右侧指令及取点坐标”，以及是否修改过字段 |
