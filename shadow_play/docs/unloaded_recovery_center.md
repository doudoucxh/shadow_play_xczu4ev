# 事故锁保留时的单路空载回中

`integrations/calibration/recovery_center_once.py` 是独立的恢复入口。仅在现场已解除所选云台与皮影的牵拉、确认剩余短杆和支架转动无干涉、有人能断电，并明确批准本次恢复之后使用。普通“继续”不视为批准。本程序不改变日常调角窗口的持续保持行为。

本次用户将 1/2 号云台的两节木杆从拼接处分开，云台上仍留短杆。这也可能解除皮影负载，但需要另行确认两段确实完全分开、短杆扫过区域无障碍；不能把拆开木杆等同于拆光支架或已检查全部行程。

程序只允许一次、一个通道、1500 μs（装配参考 135°）的提交，保持 3 秒后关闭。开始前要求寄存器仍与计划中的全关闭状态和序列号一致；其他九路脉宽不变且不使能。运行中检查状态、停止文件、期限及事故锁内容；失败不重试。Python 正常退出或中断时请求 OFF，进程失效另由已有 FPGA 心跳看门狗停止输出。关闭 PWM 不等于切断电源，也不保证轴保持位置。

这个入口显式提供一个经现场批准的单次回中例外；它不会删除、重命名或改写 `/run/shadow-pwm-motion-inhibit`、板端 `.motion-inhibit` 或主机事故记录。普通驱动对象及带杆采集程序继续受锁保护。恢复程序必须保留两份板端锁，锁缺失或内容改变就拒绝或停止。

计划包含 `approval`、`channel`、`expected_sequence`、`expected_pulses_us`、`linkage_disconnected`、`remaining_bracket_and_rod_clear`、`observer_ready`。批准字符串固定为 `single-unloaded-center-with-incident-locks-retained`；三项现场条件必须确认为真。不得提前填写真值。旧脉宽仅用于检测寄存器是否变化，不是物理位置反馈。

不带 `--execute-approved-unloaded-center` 时仅检查计划，不打开 MMIO。`--help` 也不访问寄存器。实际执行还需要该显式选项，不能将计划校验成功视为动作授权。

测试入口：

```text
python -m unittest discover -s shadow_play/tests -p test_recovery_center_once.py -v
```

11 项无硬件测试覆盖单通道固定脉宽、保持期限、最终 OFF、普通驱动仍被锁阻止、非预期角度/多路/重复提交拒绝、寄存器变化、现场条件缺失、锁缺失/变化、取消、授权超时、中断及失败不重试。它们不证明现场短杆或支架有足够间隙。
