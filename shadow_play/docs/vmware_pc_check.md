# VMware Ubuntu 20.04：无板验证

在 Ubuntu 本地文件系统放入完整 `shadow_play` 源码后，从任意目录运行：

```bash
bash ~/piying/shadow_play/tools/ubuntu_pc_check.sh
```

需要 `build-essential cmake ninja-build pkg-config libasound2-dev python3`。脚本不安装软件；缺失时报告具体项目。

每次运行创建独立的 `output/pc-check-时间戳`，保存环境、配置、编译、9 项 CTest、四种轨迹、录制回放、模拟九点输入、整组电机目标、真实本机 UDP 通信、丢人处理、90 秒测试 WAV 及安装后运行检查。

`summary.json` 和 `REPORT.md` 记录本轮结果；只有总状态为 `passed` 才代表所有步骤通过。电脑测试不证明板端 ARM64 程序、真实机构标定或实际驱动完成。

默认构建目录为 `build-vm`；可用 `--jobs 2 --build-dir build-vm-other` 指定并行度与新缓存位置。使用与 CMake 3.16 兼容的测试命令。

## 2026-10-02 本轮已完成

已通过 SSH 在用户的 VMware Ubuntu 20.04 中执行上述流程。GCC 9.4.0、CMake 3.16.3、Ninja 1.10.0、Python 3.8.10、ALSA 1.2.2；9/9 项 CTest 通过（2.98 秒）。

结果目录：`/home/xianhaochen/piying/shadow_play/output/pc-check-20261002-201915-637857`。

90 秒排练加 2 秒结束观察产生 46010 条轴记录；三模式包含 script、paused、touch、camera、stopped；录制回放 CSV 的 SHA-256 相同。实时 UDP 发送、接受 60 帧，非法、旧序号和生命周期拒绝均为 0；已验证丢人后的回中及体感模式虎杆中立。额外生成 201 个完整电机目标组帧。

已补 WAV 安装规则，并通过安装后 WAV 哈希一致和安装版程序运行检查。测试 WAV 为 90 秒、48 kHz、PCM16 单声道；音频测试使用 ALSA null，不代表已验证实际扬声器。

## VMware 共享目录

现有共享目录已挂载到 `~/vmware-shared/VMWARE_2004`，对应 Windows `D:\VMWARE_2004`。工程构建使用 `~/piying/shadow_play` 本地目录。

`tools/mount_vmware_share.sh` 可以重新挂载；`tools/piying-vmware-shared.service` 是在用户登录后执行的用户服务。它没有修改 `/etc/fstab` 或原来的 `/mnt/hgfs` 路径。若挂载服务已启用但运行中挂载失效，可执行：

```bash
systemctl --user restart piying-vmware-shared.service
ls ~/vmware-shared/VMWARE_2004
```

服务当前启动已验证；虚拟机下一次重启后的自动恢复仍需届时确认。
