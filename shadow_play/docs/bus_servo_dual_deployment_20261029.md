# 双总线SD部署与开机自启动（2026-10-29）

已完成SD安装和一次软件重启验证。人物ID1～6共用原9口E14，老虎ID7～10共用原10口E15；两组信号彼此独立，原1～8口不连接舵机信号。

> 后续更新：用户再次明确当前双总线电气兼容性已经完成，已同步电脑与SD控制配置；COM17连接验证通过。以下部署段落中的“三项false”是安装当时状态，最新以[电气确认同步记录](bus_servo_dual_electrical_20261029.md)为准。

## 开机后的行为

SD启动环境现在选取 `image-bus-20261029.ub`。Linux启动后自动校验安装包、加载BS10 FPGA镜像，再启动原有板载界面及适配双总线的HDMI输出。冷启动加载器只执行一次，失败不自动重试，不将未来开机的执行器供电情况假定为断电。

自启动不发送舵机查询、回中、卸力、回放、运动租约或丝杆命令。电脑上的 `总线舵机示教上位机.cmd` 仍需手动打开，默认离线；串口控制服务仍由上位机按需启动，没有设置串口自动登录或后台运动服务。

**新转接板电气兼容、实际回包及机械限位尚未在本轮验证。** 双总线profile的 `electrical_3v3_verified`、`hardware_verified`、`mechanical_limits_verified` 均保持false。当前实物服务仍会因电气未核实拒绝启动，这不是未烧录；本次自启动完成不代表舵机控制已验收。完成核实后才按原权限启用查询、卸力和运动，不能直接改标记绕过。现在可继续离线录入与剪辑，详见[使用手册](bus_servo_user_guide.html)。

## 已取得的证据

- 当次用户确认舵机断电、丝杆断电或未接电。部署前启动ID `07016d40-7954-4d85-9ea6-38743c2d9fff`，运行标记为旧SP10，双总线目录尚不存在。
- 25项双总线包安装在 `/run/media/mmcblk0p2/piying/bus-servo-v1`，逐项摘要及Python语法通过；MANIFEST SHA256 `f5e1d0a9fe66eeb0d9cfa837e4dc049d0728c34de2cfd305615cc93fd5e57434`。包中 `automatic_start:false/deployed:false` 是离线打包时的历史声明，本文件及独立部署记录保存后续安装和启动结果。
- 新FIT从原 `image.ub` 拆出kernel、device tree和initramfs，再追加独立启动覆盖层；kernel、device tree摘要不变，重新拆解新FIT的三个组成部分均校验通过。
- 新FIT SHA256 `bfa925cb2175d40e448f7d971922acb43ad55cf9acf3102ba44c36cb8ad22fcb`；新uEnv SHA256 `5bbdd36113c2cdb785b75b799a83815fc82dfa3f7ea5315ea67c505373871988`。BOOT.BIN、原image.ub、boot.scr及原UI FIT均保持原摘要。
- 仅一次重启，新启动ID `f589ca82-29b6-48a1-90f8-60fb6193101f`。未登录时即捕获 `BS10_AUTOSTART_SUCCESS`；随后登录独立复核，不靠手动补加载获得成功。
- FPGA operating，身份 `0x42533130`（BS10）、版本1、100MHz/115200bps、faults=0、lease=0，person/tiger状态均0。当前bus加载标记与新启动ID/镜像匹配，旧PWM加载标记不存在。
- 启动服务active/exited、Result=success、Restart=no；UI/browser/HDMI均active/running。3个递增时间戳的界面包可解码为1024×600。没有实体屏视觉验收；本次验证为软件重启，未要求用户物理断电重上电。
- 旧十口24项与四口22项安装包全部摘要复核通过；事故锁内容SHA256仍为 `643e58a534c97f5e3b799285fa78afef9d820b93274795de7d79db55ccc12bd3`。COM17已释放，无舵机服务或动作任务启动。
- 新增7项启动测试加原4项启动测试全部通过。覆盖默认不执行、已加载/已尝试拒绝、非空闲状态拒绝、固定只读寄存器集合、摘要/路径校验、启动覆盖层、不自动重试和备份失败不删除源文件。

## 备份位置与维护

启动分区原空闲92.8MiB，小于新FIT所需空间。唯一被移出的文件是未被当前启动环境引用的 `image.ub.previous-20260922_205145`，已逐字节摘要核对后转存至SD第二分区 `piying/boot-bus-20261029/`，SHA256 `a3d935db943f9db98ed0b105c0dc52dda04e2e924a27b5849e08e6cad021811e`。当前原始image.ub及原UI FIT仍在第一分区。

修改前的uEnv同时保存在第一分区和 `piying/boot-bus-20261029/uEnv-before-bus-20261029.txt`。没有执行回退；若以后需要回退，应在全部执行器断电时由维护人员校验并恢复该文件，随后重启。旧配置会重新加载SP10，不能将它用于当前总线接线的实物控制。

启动源码：`shadow_play/boot_bus/launch.py`、`shadow_play/boot_bus/shadow-theatre-boot.service`。一次性构建安装器：`shadow_play/tools/install_bus_autostart.py`。不要重跑已使用的安装目录或删除当前启动尝试标记来重试FPGA。

结构化结果见 [bus_servo_dual_deployment_20261029.json](../config/bus_servo_dual_deployment_20261029.json)；原始串口证据留在本机忽略目录 `.review_work/bus-servo-dual-deploy-20261029/`。板端时钟仍为旧值，本文采用电脑日期。
