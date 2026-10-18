# 皮影戏台 HDMI 界面部署包

> 当前源码为 r4 软件部署版，基于用户提供的 r2 原包。2026-10-17 已通过 COM17 安装到板端 SD，运行实际界面、USB 摄像头/DPU 和原声播放，见 [实板记录](../docs/hdmi_ui_deployment_20261017.md)。用户尚未安装舵机与丝杆，所有电机请求保持拒绝。完整发布保持外层 `shadow_play` 目录结构。

## r4 无桌面显示路径

`runtime/browser_display.py` 以普通用户启动独立 Firefox，保留沙箱；最终板端使用带认证的私有 Xvfb 内存画面，BiDi 负责交互与页面存活检查。`runtime/hdmi_sink.py` 只接收两秒内的新 JPEG，在既有审核通过的 PL HDMI 上输出。逻辑视口为 1024×600，按比例居中到既有 1280×720 时序；触摸坐标反向换算。过期画面清空，不用旧截图冒充正常界面。显示驱动仍要求本次启动的有效 FPGA 标记，安装器不会自动加载 FPGA。

`tools/install_hdmi_software.py`（外层 shadow_play/tools）把校验后的运行包和 Firefox 安装到 SD 新目录，生成 HTTP、普通用户浏览器、HDMI 三个独立服务。`--activate` 只启动前两者。现有系统根目录是内存盘，`systemctl enable` 不能据此宣称重启自启；SD 中保留 `start-software.sh`，没有修改 BOOT.BIN、image.ub 或 uEnv。

经典页新增“播放原声”，通过固定哈希播放器播放 67.105688 秒原音轨，增益 0.60，不调用编舞或机构代码。播放时进度来自播放器进程计时，不声称声学同步；离页、隐藏或十秒失去浏览器租约停止。第三模式继续按需启动真实摄像头/DPU，不填造缺失关键点。

Firefox 158.0 ARM64 来自 Mozilla 官方包；私有目录内补充 Debian libasound2 1.2.8 的 ARM64 动态库与许可文件，不覆盖系统库。WebSocket 客户端为 1.9.0。二进制与音轨仅放入被忽略的构建包，源码和校验依据进入 Git。

交接日期：2026-10-16。项目板卡：**正点原子 MPSoC-P4／XCZU4EV，板端 Linux**。
目标屏幕：10 寸、**1024×600**，横屏、浏览器缩放 100%。

本包是可离线运行的界面、识别模型和部署源码，发给队友时请发送整个压缩包。
**不是 FPGA bitstream、BOOT.BIN 或 SD 系统镜像。现有 SD、FPGA、DPU、摄像头及电机程序不被本包自动修改。**

## 队友先做这一步

解压后，在板上运行：

```sh
sh runtime/check-board.sh > board-check.txt 2>&1
```

项目原有 HDMI 是 PL／VDMA 显示流水线。**板子能出摄像头画面，不等于 Linux 浏览器能直接往该 HDMI 输出。**
如果当前系统已有连接到该屏幕的 X11／Wayland 桌面和 ARM64 Chromium，按下节启动；
如果仍是原有无桌面的 PL／VDMA 系统，先按 `docs/BOARD_INTEGRATION_CN.md` 接通图形输出。
Python HTTP 服务本身只提供界面文件，不会驱动 HDMI。

## 板端已有图形桌面时

1. 将整个目录放到 `/opt/shadow-theatre-hdmi`，或普通用户可读写的目录。
2. 在连接该 HDMI 的图形会话中，用普通用户打开终端。所需软件：Python 3.7+、支持现代网页功能的本机 ARM64 Chromium。
3. 在系统显示设置中选择该 HDMI、1024×600、缩放 100%，触摸屏 USB 接口也接到板子。
4. 在包根目录执行：

```sh
sh runtime/start-linux.sh
```

浏览器会以全屏模式打开 `http://127.0.0.1:8765/`。退出用 Alt+F4。
程序日志默认在 `~/.local/state/shadow-theatre-hdmi/`，操作数据保存在浏览器独立配置目录中。
启动脚本只回收它自己启动的进程，不会停止原项目显示服务。

可选参数示例：

```sh
SHADOW_UI_BROWSER=/usr/bin/chromium SHADOW_UI_PORT=8765 sh runtime/start-linux.sh
```

若桌面没有启动、没有浏览器或以 root 运行，脚本会明确提示，不会假装部署成功。
浏览器应由图形登录用户启动，不要默认加 `--no-sandbox`。

## 在电脑上先检查同一个包

Windows 可执行 `runtime/start-windows.ps1`；或者在包根目录手动运行：

```sh
python runtime/serve.py
```

然后访问 `http://127.0.0.1:8765/`。浏览器视口设为 1024×600、100% 缩放。
界面、字体、武松、老虎、实物旗帜和手绘模型都已内置，无需 npm、Codex 或联网。
本包的“画法”入口是离线图谱，不会连接原电脑的 8780 采集服务。

## 当前功能与对接边界

- 首页：点击显示／隐藏模式入口，翻书进入，合书返回，火星和旧纸效果。
- 经典表演：界面中的示意表演及章节操作。
- 笔墨成戏：手绘动作分类、标准皮影姿势、左右位置调整、动作保存及依次播放。
- 以身入戏：浏览器摄像头预览及外部真实关键点覆盖接口。
- **没有自动接通电机、丝杆或板端 DPU。** 页面中的位置滑块目前是界面位置，非电机指令。
- 摄像头必须由浏览器识别为可用设备；原来通过 PL DMA 采集的相机不一定出现在浏览器设备列表中。
- 人体模型结果需队友按 `docs/BOARD_INTEGRATION_CN.md` 接入，当前界面不会凭空生成人体识别结果。
- 当前模型和动作目录以 `VERSION.json` 记录的实际文件为准；识别效果仍需用真实用户画稿验收。

保存动作不逐张发送消息。重新启动会进入首页，已存序列和画稿会保留。
使用相同浏览器配置目录和端口可保留数据；清除浏览器站点数据会删除本机保存内容。

## 开机进入界面

先完成手动启动和板端 HDMI／触摸验收，再按实际图形桌面设置自动登录。
包内 `runtime/shadow-theatre.desktop` 是用户桌面自启动模板，默认安装位置为 `/opt/shadow-theatre-hdmi`：

```sh
chmod +x /opt/shadow-theatre-hdmi/runtime/start-linux.sh
mkdir -p ~/.config/autostart
cp /opt/shadow-theatre-hdmi/runtime/shadow-theatre.desktop ~/.config/autostart/
```

路径不同须先改模板的 Exec 和 Path。无图形会话时不要直接把模板换成开机 systemd 服务；浏览器仍然没有可用显示输出。
以上桌面模板属于原 r2 交付说明。当前 r4 使用上文的独立服务，尚未验证重启后自动上屏。

## 目录

| 目录／文件 | 用途 |
| --- | --- |
| `runtime/web/index.html` | 可运行的完整离线界面 |
| `runtime/serve.py` | 仅用 Python 标准库的本机网页服务 |
| `runtime/start-linux.sh` | 板端图形会话下全屏启动 |
| `runtime/check-board.sh` | 板型、浏览器、显示设备只读检查 |
| `runtime/start-windows.ps1` | 队友电脑预览 |
| `source/` | 本次冻结的界面、素材和模型源码，不含历史原始训练画稿 |
| `tools/build_ui.py` | Python 离线重建，无 npm 依赖 |
| `tools/verify_integrity.py` | 用 Python 检查解压后的文件完整性 |
| `docs/BOARD_INTEGRATION_CN.md` | MPSoC-P4 的 HDMI、相机及人体结果接入说明 |
| `licenses/` | 内置字体许可与素材来源 |
| `VERSION.json`、`SHA256SUMS.txt` | 冻结版本与校验清单 |

解压后可运行 `python3 tools/verify_integrity.py` 检查文件完整性。
队友修改 source 后，可在包根目录运行 `python3 tools/build_ui.py` 重建网页。
重新生成后旧的 SHA256SUMS 不再匹配，需要更新版本清单。

本次识别更新见 docs/MODEL_UPDATE_CN.md；请关闭旧界面及其网页服务后再启动新版。
