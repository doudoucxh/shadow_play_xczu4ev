# SD 开机自动进入主页

2026-10-18 按用户要求安装。板子继续使用 SD 启动，界面、浏览器和显示依赖继续存放在第二分区；无需电脑发送启动命令或登录 Linux。

## 已完成的验证

- 从旧启动 `b7558875-c170-48f4-8991-e4194f278329` 正常重启，进入新启动 `ced01bb9-9579-4335-a4dd-2405d0d2b87b`。
- 串口仅接收启动日志，没有登录、手动启动服务或发运动命令。系统 uptime 52.2 秒时，启动服务报告 `HOME_SERVICES_READY`；该时间从 Linux 启动计，不包含前面的引导加载时间。
- HTTP、普通用户 Firefox/Xvfb、HDMI 服务全部 active，并检测到连续的新 UI 帧。浏览器启动过程中有一次服务自动重试，随后正常就绪。
- 显示镜像加载后只读确认十路关闭、armed=false、enabled_mask=0、sequence=0、faults=0、pending=false。UI 状态中摄像头与音频未运行，机构不可用。1500 μs 为复位寄存器值，不是实际位置。
- 此次是软件重启验证，尚未做现场拔电再上电测试。实体屏在此次重启后的现场确认单独记录，不能用进程 active 代替实体屏验收。

## 启动方式

原 `BOOT.BIN`、`image.ub`、`boot.scr` 和 USB 设备树补丁保持不变。启动分区增加 `image-ui-20261018.ub`，内核与设备树和原镜像逐字节相同；原压缩内存盘后追加小型启动 CPIO。Linux 支持独立 CPIO/压缩档案串接，参见 [内核 initramfs 格式文档](https://www.kernel.org/doc/html/latest/driver-api/early-userspace/buffer-format.html)。不把 SD 分区改为另一套根系统。

`uEnv.txt` 只将 `piying_load` 中的 `image.ub` 文件名改为 `image-ui-20261018.ub`，保留已验证的 USB 与 SD 写保护修正逻辑。内存系统中的 `shadow-theatre-boot.service` 等待第二分区挂载，校验 SD 启动脚本摘要后执行。启动脚本核验现有 64 项运行文件、固定显示镜像和动作锁，加载已审核的同一 PL 镜像并确认输出关闭，然后恢复显示依赖链接、输入权限和三个界面服务。

旧 `shadow-video`、`shadow-yolo-follow`、`shadow-yolo-pose`、`shadow-arm-chain`、`shadow-hw-init` 服务在新内存盘中被屏蔽，避免并发占用 PL/HDMI。不会开机播放剧本、开启相机识别或启用机构。第三模式仍按用户操作启动摄像头；完整人体关键点验收不属于本次启动验证。

源码位于 `shadow_play/boot_ui/`；构建安装器为 `shadow_play/tools/install_ui_autostart.py`。启动脚本被镜像内摘要绑定，不能只改 SD 上的 `launch.py` 就声称新版本已生效，必须重建对应启动镜像。该入口仅用于冷启动，已存在运行镜像标记时拒绝重新加载 PL。

## 备份与回滚

- 原启动配置：启动分区 `/run/media/mmcblk0p1/uEnv-before-ui-20261018.txt`。
- 新镜像、启动源码、分部校验与安装摘要：第二分区 `/run/media/mmcblk0p2/piying/boot-ui-20261018/`。
- 启动分区初次写入时空间不足，尚未切换 `uEnv.txt` 就停止。历史备份 `image.ub.before-follow-20260923_174611` 已校验后迁至上述第二分区目录，SHA256 为 `cb5070b664ed64415fa2f79c95c449597f46b755399d0bd61640ba932379ef8d`，没有丢弃。失败写入的本次临时副本在核对与候选前缀一致后清除。
- 如需恢复原启动，在板子关机后用电脑访问 SD 第一分区，将现有 `uEnv.txt` 另存，再将 `uEnv-before-ui-20261018.txt` 复制为 `uEnv.txt`。原 `image.ub` 一直保留。下次启动将回到原系统行为，自动主页不再启动。

四项离线测试通过：启动档案与服务屏蔽、仅替换启动镜像文件名、CPIO 对齐/路径检查、可重复构建。板端 Python 语法通过，候选 FIT 的三部分重新提取后逐一核对摘要；内核与设备树仍为原摘要。板上没有 `systemd-analyze`，不宣称该静态检查通过，实际服务启动已验证。启动日志含既有系统服务失败提示；不据此宣称整机所有服务健康，网页显示启动成功有独立证据。

详细摘要见 `shadow_play/config/hdmi_ui_autostart_20261018.json`。原始串口日志仅保存在本地忽略目录，不加入 Git。
