# 2026-10-17 板端软件部署

用户确认 COM17 为 PS 调试串口，只有串口传输；USB 摄像头、触摸屏及扬声器已连接，舵机、丝杆尚未安装。本次部署软件与显示，不执行机构运动。

## 安装位置与显示

- SD 运行目录：`/run/media/mmcblk0p2/piying/shadow-theatre-board-20261017-r4-runtime`。
- Firefox 158.0 ARM64 与私有 Xvfb 分别安装在同级 `firefox-158.0-arm64`、`xvfb-private-20261017`。浏览器及虚拟显示由普通用户 petalinux 运行，Firefox 沙箱保留，Xvfb 禁用 TCP 并使用私有认证 cookie。
- 服务为 `shadow-theatre-ui-r4`、`shadow-theatre-browser-r4`、`shadow-theatre-hdmi-r4`。逻辑页面 1024×600，居中输出到既有 1280×720 HDMI 时序，触摸坐标按相同比例换算。
- 初始无窗口截图约 0.9 fps；原生 UTF-8 解码减少重复处理后约 2.1 fps。最终采用 Xvfb 内存画面，JPEG 输出实测约 11.97–11.98 fps。帧过期两秒后显示等待页，不保留旧画面冒充正常输出。
- 已在板端查看主界面与三个模式。保留原包图像、旧纸翻页和火星；新增中文提示使用同款 Ma Shan Zheng 的开源字形补集，避免板端缺字。

## 摄像头、音频与输入

摄像头为 icSpring USB 相机，第三模式调用真实 DPU Pose9。已验证连续帧序号、板端单调时钟时效、JPEG 解码、DPU 硬件指纹和页面中的实时预览。测试画面主要为房间场景，没有完整人体，因此不把相机接通等同于完整人体关键点验收。

首次检出人像时的输入/解码一致性校验可能超过 250 ms。仅在 `USB + display none + no-send + UI feed` 的预览路径丢弃过期结果、清除旧预览并继续下一帧；不会发布过期关键点，原控制发送路径仍拒绝过期结果。未来接机构不得因这次软件验证跳过映射与机构标定。

USB 扬声器识别为 Jieli Technology USB Composite Device，播放设备 card1/device0。原声 67.1056875 秒完整播放，ALSA 实测 RUNNING，播放器正常 PLAY_COMPLETE；增益 0.60。未测量现场响度或声学延迟。经典页按钮控制原声，离页停止。

OpenWare Multi-Touch-V5000 触摸接口为 event10，程序验证 BTN_TOUCH 与绝对坐标范围并已打开读取。界面入口使用板端虚拟指针完成验证；不把软件点击测试写成现场手指触摸验收。

## 机构与重启边界

显示所需的已审核 `servo10_vision` 镜像仅加载到易失 PL，随后读取 `armed=false, enabled_mask=0, sequence=0, faults=0, pending=false`。1500 μs 为寄存器复位值，不是实际轴角或机械回中证据。原事故锁未解除，新运行目录额外保留 `.motion-inhibit`，所有运动 API 拒绝；没有驱动舵机、丝杆或运行旧剧本。

BOOT.BIN、image.ub、boot.scr、uEnv.txt 的加载前后哈希不变。板子根文件系统是内存盘：软件文件保存在 SD，但**尚未配置开机自动上屏**。SD 中的 `start-software.sh` 重建缺失的 XKB 入口、X11 目录与服务链接，启动软件；HDMI 仍要求本次启动已核验的 PL 标记。重启后需要重新准备显示环境，不能把 `systemctl enable` 当作持久自启动。

## 交付与复现

`tools/install_hdmi_software.py` 校验并安装 UI、Firefox，可用 `--xvfb-archive` 指定私有显示包；重新生成显示包时，将 `tools/prepare_hdmi_virtual_screen.py` 输出的摘要传给 `--xvfb-sha256`。显示依赖来自 Debian 官方存档，保留逐包摘要、逐文件清单及许可证。仅在私有目录添加系统现有 bzip2 1.0.8 的兼容别名，不覆盖系统动态库。

构建包、原始串口日志与检查截图保存在本地忽略目录，不进入 Git；仓库保留源码、部署摘要和验证结果。详细机器记录见 `config/hdmi_ui_software_deployment_20261017.json`。

## 2026-10-18 收尾验收

COM17 复查仍为同一次启动，三个服务均 active。板端虚拟指针点击“播放原声”后实际播放器进入 playing；点击返回主页后，音频与摄像头均停止。安装目录 64 个文件逐一通过 SHA256 校验，清单与本地最终构建一致。再次只读核验十路 armed=false、enabled_mask=0、sequence=0、faults=0、pending=false，动作锁存在。页面最终留在主页。此项仍不替代现场手指触摸与完整人体关键点验收。

相关离线检查：UI 帧、虚拟画面和浏览器共 15 项测试通过，HTTP 服务 14 项通过，64 项 UI 文件完整性检查通过；依赖打包工具及安装器语法检查通过。
