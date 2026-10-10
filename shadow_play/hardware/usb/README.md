# MPSoC-P4 / XCZU4EV USB2 启动修复

2026-10-10：**新 FSBL 与持久 USB 覆盖已启用，正常软件重启验证通过。**系统自动识别 icSpring `32e6:9211` 摄像头，`/dev/video0` 实拍通过；USB+DPU+HDMI 约 15 fps。用户已现场确认“画面实时且骨架正常”；机构映射及真实电机跟随尚待联调，详见 [迁移记录](../../docs/usb_camera_migration.md)。

## 为什么应用程序之外还要改启动程序

实际 Linux 5.15.36-xilinx-v2022.2 已含 UVC、DWC3、xHCI，但旧 FSBL 没有初始化 USB0，并未在 PMU 配置对象中授权 USB0。读取固件得到三路 USB0 内部复位均有效，ULPI 引脚仍是 GPIO。临时 Linux 设备树的驱动探测对 pinmux、clock、power-domain 都返回 -13。探测覆盖已撤回，没有在线操作 SD 驱动。

依据为用户提供的正点原子资料盘：`MPSoC_P4_2CG_4EV_1V7.pdf` 第 5、25、26 页、Linux 指南 V2.0 第 1102–1104、1112–1114 页，以及 4ev/base_vcu 的 PS 配置。四个 Host 插座通过 GL3523 Hub 连接 USB3320/USB0；使用 MIO52–63，Hub 复位 MIO24。MIO25 的 PHY 复位保持参考工程的板上拉释放方式。先启用 USB2 high-speed，USB3 GT 不参与此次迁移。

## 改动与验证范围

- `original_ps_config.tcl` 保存现有 G13 舵机/视觉工程的 PS 参数；`create_usb_ps.tcl` 在独立临时工程导出只用于 FSBL 的 XSA，不生成、加载或替换 PL。
- 新旧 `psu_init.c` 去除注释后比较，变化仅涉及 USB 时钟、MIO24/52–63、对应三态位、USB 内部复位与 USB 封装寄存器、MIO24 GPIO 复位序列。DDR、SD1、UART 初始化代码不变。
- 新 BSP 中 SD 控制器仍是 `0xFF170000`、4 bit、无 WP；PM 配置对象已包含 `NODE_USB_0` 的 A53 授权。
- `build_usb_fsbl.tcl` 使用 Vitis 2022.2 的 FSBL BSP，启用串口 DEBUG_INFO。原 PMUFW 沿用，不使用新平台自动生成的 PMUFW。
- 原板 BOOT 与本地已验证引导组件逐分区比对。`usb_boot_candidate.py` 只替换 FSBL，保留板上原始 PMUFW、视觉 bitstream、BL31、DTB、U-Boot，包括与本地其他版本不同的那份 PL 数据。
- 启动包及预检现为十项测试，覆盖源文件变化拒绝、模板损坏拒绝、PMU 不变、分区搬移、分区校验和、保留槽校验、旧固件与错误 ULPI 功能拒绝，以及 USB 空闲/上电状态区别。原八项在 Windows/板端通过，新增两项在 Windows 通过；板端候选重建结果与保存文件逐字节一致。
- 新 FSBL 初始化后，闲置 USB0 核心复位 1059 可能仍为 1；Linux wrapper 获取电源域时，PMU 正常释放它。预检仅在 wrapper 绑定后要求三路复位全为 0，不手工写 MMIO 释放复位。
- FSBL 已设置 USB bus 约 250 MHz、ref 20 MHz；设备树不再重复设置 `assigned-clock-rates`，避免在获取电源域之前设置时钟导致 `-13`。

## 已保存的板端文件

目录 `/run/media/mmcblk0p2/piying/usb-boot-20261010/`：

| 文件 | SHA-256 / 状态 |
| --- | --- |
| `BOOT-original.BIN` | `50aad4a809b345d2491380e6d7ca85a21b4cbf7e6b816616bfa7435f2204ce96` |
| `BOOT-usb-candidate.BIN` | `32dd1cd32f9675a4c9acaafe330f8e7a7853f1766637a117cf2b57bd536fe55f` |
| 首次实测 `prepare.dtbo` | `8ace44533632ecfd166b2b840e173662ee0d8659891c1e5f5c40623f1ebe483c`；归档，最终版本见下表 |
| `start.dtbo` | `ffe61864ef835512d897bc3e2718a7bdfbde6dcb82660e011ae8978288d1db3d` |

活动 `/run/media/mmcblk0p1/BOOT.BIN` 已为 `32dd1cd3…` USB 版本，两个 BOOT 都是 9,522,192 字节。第一分区另有原版 `BOOT-before-usb-20261010.BIN`。Git 保存紧凑模板 `boot_patch_20261010/`，可用原板 BOOT 重建相同文件；生成工具不会自动激活启动。

最终覆盖与安装器保存于板端 `piying/usb-boot-finish-v2/`，本地对应 `release/`、`uEnv.usb.txt` 及 `../../tools/install_usb_boot_overlay.py`：

| 文件 | SHA-256 |
| --- | --- |
| 最终 `prepare.dtbo` | `37dd213519389c0fa69a51e20e938260b70535960265da7674a2dbecfb4a77af` |
| `start.dtbo` | `ffe61864ef835512d897bc3e2718a7bdfbde6dcb82660e011ae8978288d1db3d` |
| `boot.dtbo`，启动分区命名 `piying-usb2-20261010.dtbo` | `80ffef7773fc79e1f46e98457de94e867bf99c406aadc9a0c531f430d1ec6b79` |
| 活动 `uEnv.txt` | `c7c1db61b2dfac2bb6dad137a7d2f041345ff98eb76b4d594a1431918e800770` |
| 原 SD 修复 `uEnv-before-usb-20261010.txt` | `93e89d104c9f930009afab056bbca244bb80864ef1972868a283dc540bcef466` |

原 `image.ub` SHA 为 `0405950d4896f2b9f549ba03664d9fc746ff1c1150ae8aca608cc950c6727dcc`，原 `boot.scr` 为 `9ada4d88212468c12d2710b0fae35df42c4c72134bafa82b2ae5aca82570a7f1`，均未替换。

## 启动方式与验证

`uEnv.txt` 在原 FIT 完成 `bootm prep` 后应用 USB 覆盖，保留 U-Boot 的 chosen/initrd 修正及既有 SD `disable-wp`。仅改 USB0/pinctrl，不更换完整 FDT、不增长 FDT 到相邻 initrd。UBoot 覆盖失败时重新加载原 FIT，并尝试仅应用 SD 修复。

原厂 `boot.scr` 使用未加引号的 `test -n $uenvcmd`。首个较长入口触发参数限制，USB 与 SD 修复均未执行；已用 U-Boot 内存启动恢复可写，最终改为短 `uenvcmd=run piying_usb_boot; run piying_sd_boot`。修订后完整自动重启出现 `Piying USB2 and SD disable-wp applied`，Linux 自动枚举摄像头且 `ro=0`。失败草稿作为 `uEnv-long-entry-20261010.txt` 留存，不参与启动。

安装器严格校验当前 BOOT、image.ub、原 uEnv、覆盖及新环境哈希，先备份再原子替换。七项回归覆盖预检不写盘、备份与幂等、源文件变化拒绝、载荷变化拒绝、备份冲突、安装不完整以及短入口回归；Windows 与板端均通过。

已经安装的实物板不需再应用运行时覆盖。只读复查可执行：

```sh
cd /run/media/mmcblk0p2/piying/usb-boot-finish-v2
python3 tools/install_usb_boot_overlay.py \
  --overlay hardware/usb/release/boot.dtbo --env hardware/usb/uEnv.usb.txt
ls -l /dev/video*
cat /sys/block/mmcblk0/ro
```

`enable_p4_usb_host.py` 与 prepare/start 覆盖保留用于“新 FSBL + 原禁用设备树”的分阶段调试；USB 已开机启用时不要再次 `--apply`。任何错误都应先查看状态，不重复叠加、不在线操作 SD 驱动。

本次原根文件系统仍在 RAM，USB 视觉入口存于 SD，未改为整机开机自动预览。USB 驱动可随系统自动初始化；每次重启后 HDMI 使用 G13 运行镜像仍需关闭舵机电源并按迁移说明加载。

## 回退

只回退 USB 设备树：把第一分区 `uEnv-before-usb-20261010.txt` 复制回 `uEnv.txt`，保留原 SD 修复。完整恢复旧启动还需把 `BOOT-before-usb-20261010.BIN` 复制回 `BOOT.BIN`。操作前核对上述备份哈希，保持舵机断电，保存后 `sync` 再重启。Linux 不能启动或 SD 只读时，断开板子电源，用读卡器复制这两份已保存备份；不格式化、不删除备份。

## 重建

在 Windows 的 Vivado/Vitis 2022.2 命令环境中，依次执行 `create_usb_ps.tcl`、`build_usb_fsbl.tcl`。输出位于项目 `.review_work/usb_camera_20261010/`。如修改了 XSA，必须使用新的 Vitis 输出目录重建，不能复用旧 BSP。FSBL 编译时间可能改变二进制，重新构建后需重新校验哈希。

在 Ubuntu 执行 `sh build_overlays.sh 原板导出的.dtb 新输出目录`，使用 `dtc -@` 与 `fdtoverlay` 编译、离线应用。已验证能重建与 `release/` 完全相同的三个 DTBO；差异仅为 USB0/pinctrl。不要将 Linux 导出的完整 FDT 直接替换启动 FDT，其中有本次启动的动态 initrd 信息。

封装时使用原有 PMUFW、BL31、DTB、U-Boot 和任意同尺寸的原版 PL 作为 bootgen 模板；最终板端重建始终复制原板 PL，并核对全部保留分区。`package_boot_patch.py` 将 bootgen 模板与实际源 BOOT 的校验清单生成紧凑补丁。模板或工具改变后需重新验证，不能沿用本文候选哈希。
