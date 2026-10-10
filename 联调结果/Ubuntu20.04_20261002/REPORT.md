# Ubuntu 电脑端验证结果

- 状态：passed
- 工程：`/home/xianhaochen/piying/shadow_play`
- 输出：`/home/xianhaochen/piying/shadow_play/output/pc-check-20261002-201915-637857`
- 范围：模拟输入与电机指令计算；没有连接开发板、真实电机或摄像头。

| 步骤 | 结果 |
| --- | --- |
| 01-configure | passed |
| 02-build | passed |
| 03-ctest | passed |
| 04-rehearsal90 | passed |
| 05-preview-rehearsal90 | passed |
| 04-touch | passed |
| 05-preview-touch | passed |
| 04-camera | passed |
| 05-preview-camera | passed |
| 04-three_modes | passed |
| 05-preview-three_modes | passed |
| 06-replay | passed |
| 07-synthetic-input | passed |
| 08-grouped-targets | passed |
| 09-live-udp-and-loss | passed |
| 10-cue-wav | passed |
| 11-install | passed |
| 12-installed-app | passed |

详情见 summary.json、CTest 日志及各步骤日志。

rehearsal90.svg：90 秒排练；three_modes.svg：三模式与暂停恢复；camera.svg：模拟体感；touch.svg：模拟触控。

cue90.wav 仅为测试节拍，不是正式配音。ALSA null 测试不证明扬声器或板端音画同步。
