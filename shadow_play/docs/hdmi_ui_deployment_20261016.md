# HDMI UI 板端安装记录（2026-10-16）

本记录更新 `hdmi_ui/docs/BOARD_BRIDGE_R3_CN.md` 中发布时“未部署”的状态。**文件和 HTTP/API 已在实板安装运行；网页 HDMI 显示、触摸映射和电机实控尚未完成。**

## 已完成

- COM12 已连通，沿用用户此前提供的账户完成登录；没有在仓库保存凭据。
- 新目录：`/run/media/mmcblk0p2/piying/shadow-theatre-board-20261016-r3-runtime`。旧部署目录保留。
- 运行包 17 个文件的 SHA256 全部验证；HTML 健康接口哈希与本地构建一致。
- `shadow-theatre-ui-r3.service` 当前运行，只监听板端 `127.0.0.1:8765`。它是本次启动的临时 systemd 服务，**重启不会自启**；文件保存在 SD 卡。
- USB 相机 `/dev/video0` 输入为 1280×720 MJPG，未旋转、未镜像；真实 DPU 指纹通过。实际推理约 15 FPS，DPU 推理约 15 ms。
- 相机与 DPU 经新 HTTP 接口返回三张可解码、序号递增、不同哈希的 640×360 JPEG，年龄约 87–179 ms。三帧姿态为空；实拍人物位于最右边且上半身不完整，不能据此声称人体关键点或身体跟随已验收。
- 短时相机测试结束后，API 停止成功，确认采集进程退出；UI 服务继续运行。
- OpenWare Multi-Touch-V5000 已枚举为 event10/11/12；尚未验证触摸坐标映射。
- 实机 `/api/control` 返回 409；没有向电机、丝杆或 UDP 控制端发送动作。

具体哈希、启动 ID、帧证据与状态见 `config/hdmi_ui_deployment.20261016.json`。实拍图只留在本地忽略目录，不进入 Git。板端时间仍为 2023 年，本记录采用电脑的 2026-10-16 日期及单调时钟帧年龄，不更改板端系统时间。

## 显示与实控的剩余条件

实板没有 Chromium、Xorg/Xvfb/Weston、Qt WebEngine，也没有 `/dev/dri` 或 `/dev/fb*`。已有 libEGL/libX11 并不构成可运行的浏览器桌面。旧 `shadow-video` 因找不到 OV5640 启动失败，与当前 USB 相机独立。

因此不能将 HTTP 服务启动等同于屏幕显示成功。还需要 ARM64 网页渲染引擎和到当前 PL HDMI 的输出/触摸桥，或经验证能驱动该 HDMI 的完整图形栈。当前启动没有 `/run/shadow-pwm-loaded.json`，既有 `UsbHdmiDisplay` 也不能直接作为已准备好的显示入口；本轮没有重配 FPGA 或改 SD 启动文件。

丝杆的驱动器、接口、回零、限位、行程，以及当前舵机位置仍待用户补充；人体坐标到皮影三杆映射尚未验收。UI 的目标位置不代表机械实测位置，历史动作路线没有接成可自动回放按钮。

## 运维与传输

查看服务：`systemctl status shadow-theatre-ui-r3.service`。停止本次 UI 服务：`systemctl stop shadow-theatre-ui-r3.service`。停止服务会回收它拥有的相机进程，不操作电机。

完整源码仍在 Git；串口传输可先制作精简运行包：

```powershell
python shadow_play/tools/package_hdmi_board.py shadow_play/build-hdmi-board/shadow-theatre-board-20261016-r3-runtime.tar.gz --runtime-only
```

打包拒绝覆盖已有归档。第一次全量传输在 USB 热插拔时发生 UART overrun，未通过校验、未安装。修正后的 `board_transfer.ps1` 每块先校验 SHA256、等待序号确认，再发送下一块；末尾仍核验整个文件。损坏或乱序立即停止，不写成功目标。新协议已用本次运行包实测。

`board_serial.ps1` 和 `board_transfer.ps1` 现在先辨认 shell/login/password 提示；未识别 shell 时不发送部署命令，也不会在失败清理中将 `stty` 发往登录提示。

验证：12 项 PowerShell 提示协议测试、3 项真实生成的 Python 接收器测试，以及本次板端包哈希、API、DPU 和相机短时检查通过。软件验证不替代 HDMI、触摸或机械动作验收。
