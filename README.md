# Zynq XCZU4EV 视觉皮影项目

目标平台：MPSoC-P4 / XCZU4EV，PetaLinux 2022.2。摄像头人体姿态识别驱动皮影动作；当前正在完成十路 PWM 舵机、五组云台的机械定位采集。

## 当前版本（2026-10-10）

- 视觉模型曾在板端运行并显示骨架；完整带载视觉跟随尚未完成联调。
- 十路 PWM 固件已包含 4 号引脚更正 **G13**；当前发布固件、清单及原生 MMIO 驱动纳入本仓库。
- Windows 串口角度窗口支持持续保持、数值输入、单次点动和按住方向按钮调节。按钮模式每步 8 μs（约 1.08°），是初版步幅的两倍；松开取消后续步进。
- 已记录未接木杆的云台活动范围。按钮模式在观察边界内侧各留 10°；接杆后的行程、两轴组合和真实位置反馈尚未验证。
- 1500 μs 对应标称 135°，不是标称 0°。停止 PWM 不等于关闭舵机电源。

## 文件入口

| 路径 | 内容 |
|---|---|
| `舵机角度调试.cmd` | 当前 Windows 操作窗口；打开后不会自动连接或动作 |
| `舵机角度调试_使用说明.txt` | 数值、持续保持、按住按钮模式的详细操作 |
| `shadow_play/` | 总控软件、Qt 采集界面、板端控制、Windows 工具和测试 |
| `shadow_play/hardware/servo_pwm/release/` | 当前 G13 版十路 PWM 固件和校验清单 |
| `shadow_play/docs/servo_capture_20261008.md` | 完整调试记录、限制和当前状态 |
| `project_puppet/` | 队友交付的视觉、Vivado/Vitis/HLS 源码及部署材料 |
| `handoff_visual_follow_20260922/` | 已工作视觉链路交接代码、模型和启动材料 |
| `cad/` | 支架设计、STEP/DXF/STL、装配参考图及建模脚本 |
| `camera_liveview/` | Sony SDK 取景封装源码；SDK 本体另行安装 |
| `backup_manifest.json` | 当前关键版本校验及未纳入 Git 的依赖/大文件说明 |

## 恢复与环境

```sh
git clone https://github.com/doudoucxh/shadow_play_xczu4ev.git
```

保留目录层级。现有启动器中的 Python、串口、Vivado 以及 VM 路径来自开发电脑，换电脑时先核对这些配置。Python 工具需要 Python 3、Tkinter、pyserial；图像工具还使用 Pillow。Qt/C++ 的依赖和构建命令见 `shadow_play/README.md`，FPGA 开发工具为 Vivado/Vitis 2022.2。

这是一份源码、配置、CAD 和选定交付物的版本备份，不是整台开发电脑或 SD 卡的镜像。训练数据、Python 虚拟环境、Sony SDK 下载包、构建缓存、原始相机帧、SSH 密钥、完整 Linux 系统镜像等保留在本机，详见 `.gitignore` 和清单。不要仅凭仓库中的 BOOT.BIN 就认为已具备完整可启动 SD 卡。

独立依赖 `project_puppet/ultral_xczu4ev/vitis_ai_2_5` 的上游为 `Xilinx/Vitis-AI`，本机版本 `2057c588c241c3902353bc618afc8ab214d7aeed`；该干净的第三方 Git 工作树没有嵌套提交。需要时从上游恢复对应版本。第三方代码保留原版权和许可说明，本仓库不额外授予第三方 SDK/IP 的授权。

## 后续 Git 备份

用户要求每次完整修改后提交 Git，规则见 `AGENTS.md`。审查修改并完成必要验证后，可使用：

```powershell
.\tools\backup_project.ps1 -Message "说明本次修改" -Paths "shadow_play/tools/servo_manual_gui.py"
# 用户要求同步 GitHub 时再加 -Push
```

脚本只暂存指定路径，检查暂存区，再创建本地提交。不要把密码或原始相机画面写入提交；不要使用强制推送。备份操作无需给舵机发送动作。
