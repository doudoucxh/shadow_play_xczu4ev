# Shadow DPU 双模型版本：SD 卡启动说明

## 1. 写入启动文件

将下列三个文件复制到 SD 卡的 FAT32 启动分区根目录，并覆盖旧版本：

- `BOOT.BIN`
- `image.ub`
- `boot.scr`

`rootfs.tar.gz`、`rootfs.manifest` 和 `system.dtb` 用于检查或后续调试，本次 initramfs 启动不需要单独复制它们。

## 2. 启动开发板

1. 完全关闭开发板电源。
2. 插入 SD 卡。
3. 按开发板资料中的说明将启动模式设为 SD 启动；不要使用 JTAG 启动模式。
4. 连接串口和 HDMI 显示器，然后上电。
5. 等待 PetaLinux 启动并进入命令行。

## 3. 检查摄像头硬件初始化

登录后执行：

```sh
cat /var/log/shadow-hw-init.log
```

正常时日志末尾应出现：

```text
SHADOW_HW_READY
```

如果没有出现，可手动重试：

```sh
/etc/init.d/shadow-hw-init restart
cat /var/log/shadow-hw-init.log
```

## 4. 启动双模型姿态识别

执行：

```sh
shadow-arm-chain
```

该命令会同时运行基础姿态模型和腕部专项模型，并启用 ARM-chain 联合解码、两侧肘点排他、前臂长度约束、时序跟踪、速度裁剪和 DOWN 约束。HDMI 左上角应显示 `ARM-CHAIN`；双臂自然下垂时应显示 `ARM-CHAIN+DOWN`。

## 5. 动作验收

依次测试：

1. 双臂自然下垂并贴近身侧。
2. 双手叉腰。
3. 双臂水平伸展。
4. 双臂上举。
5. 双臂交叉。
6. 快速抬起和放下手臂。
7. 背景存在其他人物时测试抗干扰能力。

重点观察肘、腕是否串到另一侧、吸附背景或在下垂姿态中漂移。

## 6. 故障信息收集

如果摄像头、HDMI 或 DPU 未正常工作，执行并保存完整输出：

```sh
cat /var/log/shadow-hw-init.log
dmesg | tail -100
ls -l /dev/mem /dev/dpu* 2>&1
command -v xdputil >/dev/null && xdputil query
```

同时保存运行 `shadow-arm-chain` 后终端显示的完整报错。不要重新训练或替换任何模型文件，先根据这些日志定位部署问题。
