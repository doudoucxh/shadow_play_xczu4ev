# 视觉 / 触控输入协议与颈部映射（v0.3）

本版按实际连接位置定义：武松左手、右手、颈部三根杆；老虎头杆连接耳部，另一根连接尾部。摄像头模式控制武松，老虎头尾当前为中立目标。

## 1. 最新 FOLLOW 如何接入

队友的最终结果在 `board_follow.py` 的 `pose = stabilizer.update(...)` 之后取得。它是 `None` 或九行三列的像素数组，每行 `[x,y,confidence]`。点顺序固定：

```text
0 head           1 left_shoulder  2 right_shoulder
3 left_elbow     4 right_elbow    5 left_wrist
6 right_wrist    7 left_hip       8 right_hip
```

数组已经还原到旋转后的正向 1280×720 画面，左上为原点，x 向右、y 向下。不要再次旋转、去补边，或用 384 除坐标。

已提供 `integrations/follow/pose_sender.py`，使用 Python 标准库，方便直接放进队友现有的 Python 视觉进程：

```python
sender = PoseSender(port=56000)  # 循环外，只创建一次
sender.publish(pose, sequence, captured, stabilizer.track_id)
```

详细接入位置、导入和退出清理见 `integrations/follow/example_hook.md`。此补丁需要由队员二/集成人员接入他的 FOLLOW；压缩包原始代码没有被改写。

适配器省略非有限值、越界和置信度小于 0.25 的点；其余点用 `x/1280,y/720` 归一化，保留真实置信度。不生成 pelvis，也不生成伪造的 neck；颈部参考由 C++ 计算。

## 2. 传输与坐标的统一约定

- 同一块板、同一 Linux 环境中，视觉 Python 向 C++ 的 `127.0.0.1:56000` 发送 UDP。端口在两端可配置。
- 一帧一个完整 UTF-8 JSON 数据报，最多 16 KiB。文件回放采用 JSONL，见后文。
- `PoseSender.publish` 使用非阻塞发送，不建立积压队列；拥塞时丢弃本帧，不反复发送旧动作。
- 一次发送成功只说明操作系统接收了数据报，不是接收端确认。C++ 用序号和本地接收时间处理重复、乱序及输入超时。
- 坐标和置信度均在 [0,1]；仍是左上原点、y 向下。`left_*`/`right_*` 是人体自己的左右，不能随镜像交换名称。
- `mirror_x` 只反转最终杆目标的水平运动方向，不交换两手身份。
- 每个点必须包含 `x/y/confidence`，可以附加布尔 `valid`，省略时默认为 true。
- 无效点通常直接省略；即便标记 `valid:false`，所带三个数值仍必须合法。禁止用有效的零坐标假装“丢点”。
- 双方都在同一板上才可用当前回环地址；跨电脑通信需要另改接收绑定和传输设计。

## 3. 摄像头消息 v2

以下只是结构示例，不是真实板上测量数据。实际适配器会发送九点中全部有效点：

```json
{
  "version": 2,
  "source": "camera",
  "session_id": "0123456789abcdef0123456789abcdef",
  "seq": 123,
  "track_id": 1,
  "captured_s": 345.67,
  "detected": true,
  "points": {
    "left_shoulder": {"x": 0.60, "y": 0.40, "confidence": 0.95},
    "right_shoulder": {"x": 0.40, "y": 0.40, "confidence": 0.94},
    "left_wrist": {"x": 0.75, "y": 0.25, "confidence": 0.92},
    "right_wrist": {"x": 0.25, "y": 0.60, "confidence": 0.91}
  }
}
```

| 字段 | 必须遵守的含义 |
|---|---|
| version | 整数 2；不是字符串或浮点数 |
| source | v2 只能是 camera |
| session_id | 本次发送进程/实例的会话；解析器接受 1～64 位 ASCII 字母、数字、下划线或连字符，适配器生成 32 位 UUID 十六进制串 |
| seq | 非负 64 位整数，会话内严格增加，允许跳号，不能每帧重置 |
| track_id | 非负 64 位整数；FOLLOW 新建跟踪时增加，detected=true 时必须大于 0 |
| captured_s | 有限非负数，单位秒，记录板端图像复制完成的单调时钟；仅保留作诊断，不用它刷新控制超时 |
| detected | 布尔值；表示有无可用受控人物，不保证每个点有效 |
| points | 命名关键点对象；detected=false 必须为空对象 |

没有可用人物时仍逐帧发送 `detected:false, points:{}`，序号继续增加。一个人物存在但全部点被过滤时，可以是 `detected:true, points:{}`。

顶层字段严格限定为表中八项；未知字段、重复键、错误类型、非有限值、坐标越界均会拒绝。不要额外塞入 width、height、orientation、原始 keypoints 数组；尺寸和方向已由这份固定协议约定。原始 9×3 数组不能直接发给这个解析器。

### 会话、人物与模式管理

1. 总控第一次接收某来源时绑定它的协议版本/会话。非当前模式的消息也记录序号，防止旧帧切模式后复用。
2. 相同会话内重复或倒退的序号被拒绝，不刷新最后有效输入时间。
3. 摄像头的 track_id 增加、重新选中人物时，若当前是 camera 模式，总控停止并清掉旧目标；操作员确认后发送 `camera` 重新启用。较小的旧 track_id 被拒绝。
4. session_id 或同一来源协议版本改变时，锁定该来源并停止当前摄像头跟随。必须执行 `stop → reset-inputs → camera` 才能接收重启后的进程；仅发送 camera 不解除锁定。
5. 当前在演剧本或触控时，摄像头的会话异常不会停止其他模式。但以后使用这个摄像头来源前仍需重置。
6. `reset-inputs` 只允许在 stopped 状态，会清除两个来源的序号/会话/人物记录。此时切模式还会丢弃已排队的旧输入，应让发送端持续发送新帧。
7. `captured_s` 的时钟原点不一定与其他设备相同，不能直接与总控相对演出时间相减计算延迟。

## 4. 触控 v1 与旧录像兼容

v1 外层保持 `version/source/seq/points` 四个字段，source 可为 touch 或 camera；禁止加入 v2 元数据。旧摄像头 v1 只能用于兼容旧输入，没有会话和人物切换检测，新的 FOLLOW 联调使用 v2。

触控程序建议直接给出火柴人的 neck 和双肩双腕；没有直接 neck 时也可由双肩中点得到：

```json
{"version":1,"source":"touch","seq":1,"points":{"neck":{"x":0.5,"y":0.4,"confidence":1},"left_shoulder":{"x":0.6,"y":0.4,"confidence":1},"right_shoulder":{"x":0.4,"y":0.4,"confidence":1},"left_wrist":{"x":0.8,"y":0.3,"confidence":1},"right_wrist":{"x":0.2,"y":0.3,"confidence":1}}}
```

v1 无会话信息，发送进程重启、seq 归零时仍需 stop → reset-inputs → touch/camera。摄像头与触控消息的序号分别维护。

## 5. 关键点怎样变成五根杆

### 武松颈部杆：wusong_neck

1. 优先使用有效的显式 `neck`（例如触控火柴人直接输出）。
2. 否则，只有左右肩均有效时才使用双肩中点：
   `neck.x=(left_shoulder.x+right_shoulder.x)/2`，y 同理，置信度取两肩较小值。
3. 头、髋和 pelvis 均不作为颈部后备点。两肩不全且没有有效 neck 时，颈部杆本帧无有效输入。

双肩中点是上身平移的颈部参考近似，**不是模型直接识别的真实脖子，也不能识别低头/转头角度**。它适合本版先联调颈部杆；如需独立脖子/头部旋转，要额外定义模型信息和机构自由度。

```text
neck_target.x = neck_gain_x × (neck.x - neck_origin_x)
neck_target.y = neck_gain_y × (neck_origin_y - neck.y)
```

目标限制到 [-1,1]，mirror_x 可再反转 x。自然站姿时记录双肩中点作为 neck_origin_x/y。模拟配置为 (0.5,0.4)，不是实测标定值。

### 武松双手：wusong_left / wusong_right

设 W 为归一化画面内的两肩二维距离，S=W×hand_span_shoulders：

```text
hand_target.x = (wrist.x - same_side_shoulder.x) / S
hand_target.y = (same_side_shoulder.y - wrist.y) / S
```

两肩都有效且 W 足够大时才计算手杆；某个腕点缺失只影响对应手，目标再限幅到 [-1,1]。这是相对肩部的动作比例映射，不是真实毫米坐标或完整多杆逆运动学；各轴局部标定、机构耦合和幅度仍需实物验证。

### 老虎：tiger_head / tiger_tail

tiger_head 指耳部连接的头杆，tiger_tail 指尾杆。摄像头/触控模式当前每帧为它们生成中立目标 (0,0)，不把操作者 head 点拿来控制虎头。脚本模式可单独编排这两根杆的动作。下半身没有新增控制杆或电机指令。

### 参数

重定向配置文件现在要求 **version=2**，字段改为 neck_*。旧 body_* 配置会明确报错，应重新按自然站姿和颈部杆标定，不直接拿旧骨盆原点套用。

| 配置 | 模拟文件值 | 含义 |
|---|---:|---|
| confidence_threshold | 0.5 | 控制侧点有效阈值；视觉发送过滤阈值为 0.25 |
| min_shoulder_width | 0.05 | 两肩最小归一化距离 |
| hand_span_shoulders | 2.0 | 手杆比例 |
| neck_gain_x/y | 2.0 / 2.0 | 颈部参考位移增益 |
| neck_origin_x/y | 0.5 / 0.4 | 模拟自然站姿颈部参考 |
| mirror_x | false | 是否反转目标水平方向 |

缺失点不会刷新对应杆的最后有效时间；当前软件策略为短暂保持，默认 0.30 秒后按限速回中。停止/换人会清除旧目标并限速回中。真实机构的失联策略仍由硬件队友验证，这不是硬件急停。

## 6. 录制回放

每行外层仍是：

```json
{"arrival_ms":0,"frame":{"version":1,"source":"touch","seq":1,"points":{"neck":{"x":0.5,"y":0.4,"confidence":1}}}}
```

实时 UDP 只发送内部 frame；外层 arrival_ms 是接收端相对时间。v2 的会话、人物编号、captured_s 与序号在录制和回放中原样保留，控制超时仍使用 arrival_ms 对应的本地接收时刻。

`assets/camera_demo.jsonl` 是 v2 人工模拟九点数据，包含手腕低置信度、丢失人物和恢复；`touch_demo.jsonl` 是 v1 模拟触控数据。它们不是实际相机采集结果。

实际联调顺序及给硬件队友的接口见 `vision_to_motor.md` 与 `hardware_motor_protocol.md`。
