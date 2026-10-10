# MPSoC-P4 / XCZU4EV USB2 启动修复候选

2026-10-10：候选已编译、封装并在板端构建/回读验证，**尚未启用启动验证**。不得把这里的构建成功当作 USB 枚举或人体识别成功。

## 为什么应用程序之外还要改启动程序

实际 Linux 5.15.36-xilinx-v2022.2 已含 UVC、DWC3、xHCI，但旧 FSBL 没有初始化 USB0，并未在 PMU 配置对象中授权 USB0。读取固件得到三路 USB0 内部复位均有效，ULPI 引脚仍是 GPIO。临时 Linux 设备树的驱动探测对 pinmux、clock、power-domain 都返回 -13。探测覆盖已撤回，没有在线操作 SD 驱动。

依据为用户提供的正点原子资料盘：`MPSoC_P4_2CG_4EV_1V7.pdf` 第 5、25、26 页、Linux 指南 V2.0 第 1102–1104、1112–1114 页，以及 4ev/base_vcu 的 PS 配置。四个 Host 插座通过 GL3523 Hub 连接 USB3320/USB0；使用 MIO52–63，Hub 复位 MIO24。MIO25 的 PHY 复位保持参考工程的板上拉释放方式。先启用 USB2 high-speed，USB3 GT 不参与此次迁移。

## 改动与验证范围

- `original_ps_config.tcl` 保存现有 G13 舵机/视觉工程的 PS 参数；`create_usb_ps.tcl` 在独立临时工程导出只用于 FSBL 的 XSA，不生成、加载或替换 PL。
- 新旧 `psu_init.c` 去除注释后比较，变化仅涉及 USB 时钟、MIO24/52–63、对应三态位、USB 内部复位与 USB 封装寄存器、MIO24 GPIO 复位序列。DDR、SD1、UART 初始化代码不变。
- 新 BSP 中 SD 控制器仍是 `0xFF170000`、4 bit、无 WP；PM 配置对象已包含 `NODE_USB_0` 的 A53 授权。
- `build_usb_fsbl.tcl` 使用 Vitis 2022.2 的 FSBL BSP，启用串口 DEBUG_INFO。原 PMUFW 沿用，不使用新平台自动生成的 PMUFW。
- 原板 BOOT 与本地已验证引导组件逐分区比对。`usb_boot_candidate.py` 只替换 FSBL，保留板上原始 PMUFW、视觉 bitstream、BL31、DTB、U-Boot，包括与本地其他版本不同的那份 PL 数据。
- 八项测试覆盖源文件变化拒绝、模板损坏拒绝、PMU 不变、分区搬移、分区校验和、保留槽校验、旧固件与未初始化 ULPI 引脚拒绝。Windows/板端均通过；板端候选再次重建结果与保存文件逐字节一致。

## 已保存的板端文件

目录 `/run/media/mmcblk0p2/piying/usb-boot-20261010/`：

| 文件 | SHA-256 / 状态 |
| --- | --- |
| `BOOT-original.BIN` | `50aad4a809b345d2491380e6d7ca85a21b4cbf7e6b816616bfa7435f2204ce96` |
| `BOOT-usb-candidate.BIN` | `32dd1cd32f9675a4c9acaafe330f8e7a7853f1766637a117cf2b57bd536fe55f` |
| `prepare.dtbo` | `8ace44533632ecfd166b2b840e173662ee0d8659891c1e5f5c40623f1ebe483c` |
| `start.dtbo` | `ffe61864ef835512d897bc3e2718a7bdfbde6dcb82660e011ae8978288d1db3d` |

活动 `/run/media/mmcblk0p1/BOOT.BIN` 仍为原版；`uEnv.txt` 仍为原 SD `disable-wp` 修复版本。两个 BOOT 都是 9,522,192 字节。Git 保存了紧凑模板 `boot_patch_20261010/`，可用原板 BOOT 重建同一候选；生成工具默认拒绝覆盖任何已有输出，也不会自动激活启动。

## 下一步实测顺序

1. 确认舵机独立电源关闭，保持板子、USB 摄像头、PS 串口连接。
2. 将原 BOOT 另备份到 FAT 启动分区，再将已校验的候选通过临时文件替换活动 BOOT，同步完成后重启。`image.ub`、`boot.scr`、`uEnv.txt` 保持原样。若启动失败，断开板子电源，用读卡器恢复原 BOOT；不要删除备份。
3. 登录 Linux 后先检查新 FSBL 对 USB0 的初始化。下面的工具会拒绝旧固件；不直接写 MMIO、不加载 FPGA、不启动舵机。

```sh
cd /run/media/mmcblk0p2/piying/usb-boot-20261010
python3 enable_p4_usb_host.py --overlay-dir .
python3 enable_p4_usb_host.py --overlay-dir . --apply
```

4. 工具先加载 prepare，仅启用 USB wrapper；确认驱动绑定、复位释放、ULPI 配置后才启用 DWC3 子节点。出现错误时停止，不重复叠加覆盖，不操作 SD 驱动。
5. 用已部署的 `shadow-usb-camera-20261010` 做设备枚举、格式查询、60 帧实拍、USB+DPU `--display none --no-send`，最后再做 HDMI。重启恢复的是原视觉 PL，只有重新验证并加载 G13 镜像后，才能使用带该镜像白名单的 HDMI 路径。
6. 实拍通过后再做持久 USB 设备树和启动入口集成。当前覆盖仅本次运行有效，尚未设置自启。

## 重建

在 Windows 的 Vivado/Vitis 2022.2 命令环境中，依次执行 `create_usb_ps.tcl`、`build_usb_fsbl.tcl`。输出位于项目 `.review_work/usb_camera_20261010/`。如修改了 XSA，必须使用新的 Vitis 输出目录重建，不能复用旧 BSP。两个 DTS 使用 `dtc -@` 编译；对从实际板子导出的 FDT 运行 `fdtoverlay` 验证，已检查差异只涉及 USB0/pinctrl。

封装时使用原有 PMUFW、BL31、DTB、U-Boot 和任意同尺寸的原版 PL 作为 bootgen 模板；最终板端重建始终复制原板 PL，并核对全部保留分区。`package_boot_patch.py` 将 bootgen 模板与实际源 BOOT 的校验清单生成紧凑补丁。模板或工具改变后需重新验证，不能沿用本文候选哈希。
