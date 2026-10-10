# 验证记录

## 2026-10-03 实物 Zynq 板端验证

在 PetaLinux 2022.2、aarch64、glibc 2.34 的实物板运行 Vitis 2022.2 GCC 11.2 交叉编译程序。`tools/target_check.py` 的 17 个执行步骤全部通过，涵盖五组 C++ 行为测试、Python 发送器、模拟 FOLLOW 到总控、实际本机 UDP、90 秒排练、三模式、SVG 和录制回放一致性。目标包关闭 ALSA，以上不包含实物音频播放。

真人视觉联调运行了约一分钟：总控收到 1620 帧，全部为 `detected=false`，没有非法/旧序号/生命周期拒绝，十轴均保持 90 度。随后视觉因摄像头 DMA 错误退出，180 秒稳定性测试未通过。原视觉服务在接入总控前也重现该错误，不能把本轮记作抬手映射验收通过。

已导出原视觉备份、板端全套测试和真实输入记录，详见 [板端联调记录](board_integration.md)。后续修正 SD 设备树写保护配置，将运行文件保存到第二分区，并完成正常软件重启及 23 个文件的哈希校验。重启后 SD 可写、程序与日志仍在，原 BOOT.BIN、image.ub、boot.scr 未变；总控尚未做开机自动启动。

新增板端进程管理入口验证：20 秒实时模拟输入测试接受 90/90 帧，产生 10010 行计算角度，左右手变化、丢失回中、虎杆中立、角度和速度限制通过；另验证模式切换和主动终止。修正了六位小数 CSV 时间戳引起的速度核查误报，新增 3 个回归用例通过。控制器限速算法未改，真实人体及舵机验证仍不包含在内。

## 2026-10-02：用户 VMware Ubuntu 20.04 的无板验证

已在 `/home/xianhaochen/piying/shadow_play` 使用 GCC 9.4.0、CMake 3.16.3、Ninja 1.10.0、Python 3.8.10、ALSA 1.2.2 完成构建。9/9 项 CTest 通过，总测试时间 2.98 秒，启用 ALSA null 软件设备测试。

执行入口：`bash tools/ubuntu_pc_check.sh --jobs 2`。结果目录为 `output/pc-check-20261002-201915-637857`，包含 summary.json、REPORT.md、CTest 日志及演示数据。

额外完成 90 秒排练、触控/体感示例、三模式及暂停恢复、录制回放哈希一致、模拟九点到 201 组完整电机目标、实时本机 UDP 60 帧（接受 60，非法/旧序号/生命周期拒绝为 0）、丢人回中、虎杆保持中立、测试 WAV 格式检查、安装后 WAV 完整性及程序运行验证。

本轮修复 CMake 安装规则遗漏 WAV 的问题。以上运行在 x86_64 虚拟机；板端 ARM64、真实视觉数据、实际驱动/机构和真实扬声器同步尚待相应阶段验证。用户另已亲眼确认视觉模型在 Zynq 运行并显示骨架。

详细环境和操作见 `vmware_pc_check.md`。

## 2026-09-23：v0.3 颈部映射与视觉交接

在已有 WSL Ubuntu 中执行了 CMake 配置、C++17 编译和以下测试；结果为 **9/9 项 CTest 通过**，总测试时间 8.44 秒。没有在 XCZU4EV 或 VirtualBox 上运行这些测试。

```bash
cmake -S . -B build-linux -G Ninja -DCMAKE_BUILD_TYPE=Debug \
  -DSHADOW_REQUIRE_ALSA=ON -DBUILD_TESTING=ON
cmake --build build-linux --parallel 4
SHADOW_TEST_ALSA_NULL=1 ctest --test-dir build-linux --output-on-failure
```

| CTest 项目 | 本版覆盖 |
|---|---|
| mapping_behaviour | 轴标定、限位、平滑、限速、逐杆超时 |
| script_audio_behaviour | 剧本、音频时钟、WAV 与 ALSA null 软件设备 |
| input_behaviour | camera v2 严格协议和回放元数据；显式 neck/双肩中点；不使用头或髋替代颈部 |
| controller_behaviour | 新会话锁定直到重置、换人停止等待重新启用、旧会话/旧人物拒绝、丢点不续期，以及原有模式管理 |
| motor_protocol_behaviour | 完整轴组 JSONL、最终 angle_deg、顺序与刷新、整帧校验及输出错误 |
| follow_sender_behaviour | Python 适配器 11 项检查，含实际本机 UDP、无效点过滤和拥塞丢帧 |
| follow_to_motor_chain | Python 九点 → C++ → 分组电机命令；头和髋固定而双肩移动时颈部跟随；虎头尾中立；丢失超时；录制回放一致；实际本机 UDP 全链路 |
| cli_integration | 90 秒排练、三模式、暂停、录制回放、CSV 与 SVG |
| live_udp_integration | 原 C++ 发送/接收、控制命令、序号、录制和退出行为 |

`integrations/follow/board_follow_with_sender.py` 是已合入发送调用的入口副本，已做 AST/编译语法检查，没有执行其摄像头、DPU 或 `/dev/mem` 代码；原始视觉交接文件保持不变。

以上确认的是软件接口链路。真实 FOLLOW 在板端的运行、ARM64 构建、颈部杆几何标定、PWM/AXI、真实电机和音频同步仍未验证。CSV/JSONL 后端均不操作执行器，双肩中点只是二维颈部参考。

## 2026-09-22：v0.2 历史验证

验证日期：2026-09-22。以下结果来自电脑上的 WSL Ubuntu，不是 XCZU4EV 实物测试。

## 环境

- Ubuntu 26.04.1 LTS（WSL）
- GCC 15.2.0，C++17
- CMake 4.2.3，Ninja 1.13.2
- ALSA 开发库 1.2.15.3
- 构建目录：`build-linux`

本次已在该 Ubuntu 安装 `build-essential`、`cmake`、`ninja-build`、`pkg-config` 和 `libasound2-dev`。这仅用于电脑开发；不能据此认定该 Ubuntu 版本受到你们所用 PetaLinux 版本支持。目标板编译应使用与实际板卡系统匹配的 SDK。

## 已运行的检查

```bash
cd /mnt/d/ZYNQ/shadow_play
cmake -S . -B build-linux -G Ninja \
  -DCMAKE_BUILD_TYPE=Debug -DSHADOW_REQUIRE_ALSA=ON -DBUILD_TESTING=ON
cmake --build build-linux --parallel 4
SHADOW_TEST_ALSA_NULL=1 ctest --test-dir build-linux --output-on-failure
```

结果：**6/6 项 CTest 通过**。其中四组行为测试合计 73 个检查项，另外两项为端到端测试。

| CTest 项目 | 检查内容 | 结果 |
| --- | --- | --- |
| `mapping_behaviour` | 19 项：标定、限位、平滑、限速、输入有效性、逐杆超时等 | 通过 |
| `script_audio_behaviour` | 26 项：剧本解析/插值、WAV 校验、音频时钟和 ALSA null 设备 API | 通过 |
| `input_behaviour` | 11 组：JSON 协议、录制格式、关键点转换、置信度、镜像、站姿参考点 | 通过 |
| `controller_behaviour` | 17 组：模式切换、暂停保持、恢复、序号检查、录制和配置校验 | 通过 |
| `cli_integration` | 完整 90 秒剧本、三模式、暂停、录制回放和 SVG 输出 | 通过 |
| `live_udp_integration` | 实际启动总控进程，通过本机 UDP 发送输入和命令 | 通过 |

未设置 `SHADOW_TEST_ALSA_NULL=1` 时，跳过 ALSA null 设备检查，其他测试仍运行。ALSA null 是软件丢弃音频的设备，只验证相关 API 路径，不代表已验证扬声器播放或真实音画同步。

端到端测试进一步验证了：

- 90 秒排练加 2 秒停止回中，模拟十轴共输出 46010 行数据；最后一帧为停止状态，剧本时间为 90 秒。
- 固定控制周期的离线录制与回放，输出 CSV 的 SHA-256 一致。
- 实时 UDP 测试接收 62 帧当前模式输入，识别 1 帧非当前来源、2 帧重复/旧序号，拒绝 1 帧非法 JSON；同时检查录制、模式切换、暂停保持和退出命令。
- 轨迹查看程序能从实际总控输出生成各轴 SVG 曲线。

测试日志保存在 `build-linux/Testing/Temporary/LastTest.log`，后续运行 CTest 会更新该文件。

## 演示文件

- `output/rehearsal90.csv` 和 `output/rehearsal90.svg`：90 秒排练加 2 秒结束观察。
- `output/three_modes.csv` 和 `output/three_modes.svg`：自动剧目、暂停、恢复、触控、体感和停止。

上述均为模拟配置的计算结果，不能作为真实机构的可达范围、实测角度或安全限位。

## 尚未验证的部分

- XCZU4EV 上的 ARM64 交叉编译、部署和运行。
- 实际板卡的声卡、扬声器、摄像头、触控屏及其驱动。
- 真实机构的轴数、几何关系、转向、归位、限位和动态响应。
- PS 到 PL 的寄存器或驱动接口，以及 PWM、电机反馈和硬件停机行为。
- 真实音频设备的延迟、暂停支持、欠载处理及整场音画同步。
- 最终 90 秒剧本、正式配音和实物动作效果。

该历史版本只连接 CSV 模拟电机后端；v0.3 新增 JSONL 软件导出。真实后端、标定参数和板卡资源就绪后，按 `team_handoff.md` 的顺序完成集成。
