# 老虎四舵机临时接原1～4号接口

**后续状态（2026-10-27）：**已安装SD包并加载BT04，详情见[部署记录](bus_servo_tiger_deployment_20261027.md)。下文“未部署”描述保留为10月26日离线完成时的历史状态；本次加载未改开机流程，实物通信与机械测试仍未完成。

2026-10-26。用户已明确：只接老虎四台，人物六台暂不连接；四根信号线互不相连。舵机逻辑编号和实物 ID 保持7、8、9、10，不改成1、2、3、4。

| 舵机逻辑编号 / 实物ID | 原接头 | FPGA引脚 | 软件总线 |
| --- | --- | --- | --- |
| 7 | 原1号舵机口 | D14 | tiger7 |
| 8 | 原2号舵机口 | D15 | tiger8 |
| 9 | 原3号舵机口 | F13 | tiger9 |
| 10 | 原4号舵机口 | G13 | tiger10 |

这四路现在各是一条单线半双工总线。新 FPGA 将原1～4号信号脚改为独立的双向串口，115200/8N1；不能用旧 PWM 镜像或旧回中程序控制这四台总线舵机。四根信号线不得互相短接。原人物/老虎双总线方案继续保留，适用于之后的新板。

## 电脑端入口

双击项目根目录 `老虎四舵机临时调试.cmd`。它加载 `shadow_play/config/bus_servo_tiger_four.json`，默认离线模拟。

- 主界面仅显示7～10号及对应的原接口，默认选择四台。
- 单轴/多轴设角、实际反馈连续录制、手动卸力示教、轨迹回放、分步姿势录入与剪辑都沿用原流程。
- 连接、反馈轮询和清空选择后的后台读取仅涉及这四台，不再尝试查询人物1～6号。
- ID配置窗口仍显示7～10号。修改软件ID不会给实物改号；已经设为7～10的舵机无须重新编号。
- 实物模式中的“PS串口”是 Zynq 的登录串口，不是官方舵机调试板的 USB 串口。这个入口不是直接操作官方调试板的串口助手。

先练习时，连接离线模拟，进入“分步录入 / 剪辑”，打开 `shadow_play/examples/bus_servo_editing/tiger_four_simulation.project.json`。这是三姿势、5.5秒的模拟数据，仅供操作练习，不能驱动实物。

原入口 `总线舵机示教上位机.cmd` 仍加载十轴双总线配置。两种接线配置的轨迹摘要不同，不能直接互相回放；原始素材保留，不改写其中的配置摘要强行导入。换回正式双总线后，按实际装配和限位重新确认素材。

## FPGA与板端候选

新独立候选的身份为 **BT04**（0x42543034），寄存器基址仍是0xA0060000；四路寄存器窗口分别从0x100、0x200、0x300、0x400开始，0x24返回通道数4。它与原 **BS10** 双总线镜像具有不同身份和引脚清单。

驱动会在打开MMIO之前比较配置布局、镜像清单、当前加载标记、启动ID和镜像摘要；访问后再核对硬件身份、通道数、时钟与波特率。选择错误布局时拒绝使用旧地址，不自动换镜像或退回PWM。各口独立收发；主机停止或活动租约超时请求四路各广播一次卸力，实际停止效果仍需实物确认。

发布目录：`shadow_play/hardware/bus_servo_tiger/release/`。

本次完整构建已通过：WNS 0.498 ns、WHS 0.006 ns、WPWS 0.151 ns，失败端点均为0；200271条可布线网络全部完成、0路由错误。DRC无Error/Critical Warning，普通IP、时钟等Warning保留在报告中。除更换舵机物理接口外，其余172个具名引脚的引脚号、方向和IO标准与基线逐项一致。镜像SHA256为 `dbe937d9f01d65b60e9394c25f298369418f6f31a45f8bc027415d3a95ecbe3d`。

本机待安装包：`.review_work/bus_servo_tiger_bundle_20261026`，同名 `.tar.gz`。包内 `start_console.sh` 使用四轴配置；板端预定独立目录为 `/run/media/mmcblk0p2/piying/bus-servo-tiger-four-v1`。上位机按当前布局选择这个固定目录，不会启动原十轴包。

包内22个文件及MANIFEST、压缩包内容、硬件源码与报告摘要均已核验。新BT04和原BS10镜像通过更新后加载器的默认离线校验，没有使用 `--execute`。

**本轮仅完成本地修改和离线验证，没有安装到SD、烧录FPGA、打开实物串口或发运动命令。** 原双总线发布镜像、旧PWM工程、事故锁和开机文件保持。历史OFF210不能作为当前板端状态。

## 实物启用前

当前三个就绪字段仍为false。新舵机的信号回传电压、四个接口实际通信、安装方向与机械行程均未通过本次验证。官方USB调试板能与舵机通信，不等于舵机信号可以直接接3.3V FPGA引脚；电气兼容需要单独确认。舵机由符合型号要求的外接电源供电，并与控制端共地，不把执行器电源接到信号脚。

首次加载候选前，需要当次确认执行器断电、原输出关闭、当前启动ID/镜像摘要/OFF序号，停止占用PL的程序。继续使用 `bus_servo.load_candidate` 的显式执行流程，保留原事故锁及开机文件；默认只校验候选，不接触硬件。它不会自动部署、启动或恢复运动。

## 验证与重建

软件验证覆盖原双总线兼容、四轴配置和接口匹配、逐口收发路由、拒绝人物轴、镜像混用拒绝、四轴连续录制、姿势编辑与模拟回放、后台轮询及独立板端包选择。原41项和新增13项均通过，共54项。

四轴主窗口和编辑窗口启动检查通过，实际主界面的编号、接口标签和布局已查看。用户随后按物理Esc停止Computer Use，未继续任何窗口自动操作；编辑窗口完整人工点击流程未完成。后续只进行文件、离线构建和备份检查。

RTL仿真覆盖四个通道分别发送/接收、总线隔离、发送后释放信号线、看门狗、晚到心跳、第四通道活动期间的帧错误引发四路停止请求、显式停止。完整构建和发布摘要记录在 `config/bus_servo_tiger_four_20261026.json`，不是实物验收。

Vivado2022.2按顺序执行 `hardware/bus_servo_tiger/simulate.tcl`、`create_project.tcl`、`build_project.tcl`，输出到 `.review_work/bus_servo_tiger_sim` 与 `.review_work/bus_servo_tiger_20261026`。已存在工程需明确续接，不覆盖原双总线工程。新工程复用冻结的视觉/DPU/双丝杆UART基础设计与单线UART模块，移除十个旧PWM物理输出，增加四个总线引脚；其它引脚由发布检查逐项比较。

用bootgen把已核验的 `.bit` 转为 `.bit.bin` 后，执行：

```text
python shadow_play/tools/package_bus_servo.py --layout tiger-four-port --build .review_work/bus_servo_tiger_20261026 --release shadow_play/hardware/bus_servo_tiger/release --bundle .review_work/bus_servo_tiger_bundle_20261026
```

软件测试：`python -m unittest shadow_play.tests.test_bus_servo shadow_play.tests.test_bus_servo_editing shadow_play.tests.test_bus_servo_tiger`。受限环境将 `tempfile.tempdir` 指向项目内 `.review_work/bus_servo_test_tmp`。本轮未修改原两总线RTL或原发布镜像。
