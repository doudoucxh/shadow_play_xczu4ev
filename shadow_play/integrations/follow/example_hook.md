# 把 FOLLOW 九点结果接入 C++

此目录提供已经接好发送调用的 FOLLOW 入口副本和接口适配层，没有修改视觉交接包原件。核心映射和总控仍为 C++17；`pose_sender.py` 只依赖 Python 标准库。完整视觉入口仍依赖队友原有的 NumPy、OpenCV、XIR/VART 和板端硬件环境。

## 已经合并好的入口

`board_follow_with_sender.py` 是交接包 `handoff_visual_follow_20260922/follow/board_follow.py` 的集成副本。保留原有摄像头、DPU、180° 旋转、跟踪防抖、HDMI 显示和退出恢复逻辑；新增内容只有发送器导入、`--pose-port` 参数、循环外创建、每帧发布和退出关闭。发送调用在 `stabilizer.update(...)` 及其耗时统计后、骨架绘制前执行。

给视觉 / 硬件队友交付这两个文件：

```text
board_follow_with_sender.py
pose_sender.py
```

把它们放进**当前最新 FOLLOW 已经运行成功的同一个目录**。该目录继续使用原有 `orientation.py`、`fast_decode.py`、`pipeline_input.py`、`display_queue.py`、`pose_responsive.py`，以及 `/opt/shadow/yolo_pose9/runtime`、原有模型和匹配的板端系统；这两个文件不是完整视觉系统安装包。

先沿用队友原有方式停止旧入口，再把原启动命令 / 服务中的 `board_follow.py` 改成 `board_follow_with_sender.py`，其他原有环境设置和权限保持原部署方式。入口参数示例：

```bash
python3 board_follow_with_sender.py --pose-port 56000
```

不要同时运行两个 FOLLOW 入口；它们使用同一套摄像头、DPU 和显示资源。新入口会操作原有视觉硬件，只在匹配的板端环境启动，不能用它代替下面的 PC 模拟器。原有 `--frames` 参数保留；默认 UDP 端口为 `56000`，必须与 C++ 的 `--listen` 一致。

该入口已做不执行硬件代码的语法检查，尚未上板验证。若队友已经修改了交接包以后的视觉代码，应按下面的调用位置合并发送逻辑，避免用旧副本覆盖其后续改动。

## 接在哪里

如果使用上述集成入口，不需要重复添加下面代码。下面代码用于队友在更新过的 FOLLOW 中手动合并；把 `pose_sender.py` 与实际运行入口放在可相互导入的位置。它只是接入示例，不能当作完整入口覆盖原文件。

```python
from pose_sender import PoseSender

# 与 DPU、摄像头等资源一样，只在循环外创建一次。
sender = PoseSender(port=56000)
try:
    # 保留原有 FOLLOW 的循环、停止条件和资源管理。
    while running:
        frame, sequence, captured = producer.read()
        # ... 保留原有预处理、DPU 推理、decode_int8 等代码 ...
        pose = stabilizer.update(boxes, scores, points, captured)

        # 在 stabilizer.update 后发送这一帧，包括 pose is None 的帧。
        sender.publish(pose, sequence, captured, stabilizer.track_id)

        # ... 保留原有骨架绘制、renderer.submit、YOLO_STATUS 等代码 ...
        # 可把 sender.stats 加到原有低频诊断日志，不要逐帧打印日志。
finally:
    sender.close()
    # ... 保留原有相机、显示、DPU 等资源清理 ...
```

原 FOLLOW 的取数位置是 `pose = stabilizer.update(...)`。不使用未经人物选择的 `points`，不使用每两秒的 `YOLO_STATUS`，也不使用旧版 `runtime.py --jsonl`。

`publish` 使用非阻塞本机 UDP，每次只尝试发送当前一帧。缓冲区暂时不足时丢弃本帧，不重发旧姿态、不积压 Python 队列；返回 `False` 并增加 `dropped`。`True` 表示操作系统接受了数据报，不代表接收端已经收到。错误的元数据或数组结构抛出 `ValueError`，其他非暂时性通信错误抛出 `OSError`，应记录并修复，不能伪造有效动作继续发送。

## 坐标与协议

- 输入是最终正向 **1280×720** 画面中的 `(9,3)` 数组：每行 `[像素x, 像素y, 置信度]`。已经旋转、恢复网络缩放与补边；这里不再次旋转。
- 行顺序：头、左肩、右肩、左肘、右肘、左腕、右腕、左髋、右髋。左右是人体自身的左右。
- 适配器除以 `1280`、`720`，保持左上角原点，x 向右、y 向下。它省略坐标越界、非有限数、置信度不在 `[0.25,1]` 的点，保留有效点真实置信度。C++ 的默认控制阈值仍为 `0.5`。
- **不计算骨盆作为身体控制点。武松主杆固定在脖子处；C++ 用双肩中点估计颈部目标，左右腕控制左右手。** 肩中点是二维估计点，需通过自然站姿和实物增益标定匹配实际脖子杆。
- 摄像头只控制武松三根杆。老虎头杆固定在耳朵处、尾杆固定在尾巴处；摄像头模式中保持已配置中立目标。老虎动作另由剧本提供。
- 一帧是一个完整的 UTF-8 JSON 数据报，目标 `127.0.0.1:56000`，上限 16 KiB。没有 TCP 流分隔或逐点发送。

```json
{
  "version": 2,
  "source": "camera",
  "session_id": "0123456789abcdef0123456789abcdef",
  "seq": 123,
  "track_id": 1,
  "captured_s": 1234.5,
  "detected": true,
  "points": {
    "left_shoulder": {"x": 0.6, "y": 0.4, "confidence": 0.95},
    "right_shoulder": {"x": 0.4, "y": 0.4, "confidence": 0.95},
    "left_wrist": {"x": 0.75, "y": 0.25, "confidence": 0.92},
    "right_wrist": {"x": 0.25, "y": 0.6, "confidence": 0.92}
  }
}
```

上例只列出四个有效点；正常帧可包含全部九个点。不要添加 `width`、`height`、`orientation` 等未约定的顶层字段。画面尺寸和方向由此版本协议固定；视觉流程若变更这些条件，必须同时修改双方约定。

`pose is None` 时仍发送 `detected:false, points:{}`。`pose` 非空但全部点失效时可以是 `detected:true, points:{}`：检测到人物不等于每个关节都可控制。不要用上一帧姿态替代缺失数据。

## 序号、重启、换人

`session_id` 由一个 `PoseSender` 实例在启动时生成一次；不要放进循环反复生成。序号采用 FOLLOW 的 `sequence`，同一会话严格递增，允许跳号；重复或倒退会被发送器拒绝。时间使用原有 `captured` 单调时钟值，不能替换成 Unix 时间或把毫秒当秒。

`track_id` 采用 `stabilizer.track_id`。检测到人物时必须大于零；无人时可保留之前的编号或在从未建立跟踪时为零。不要强制写常数掩盖换人。

C++ 首次接收 v2 后绑定该视觉会话。以下操作需要操作员明确处理：

1. **视觉进程重启 / 创建新 Sender：**会话编号变化时，正在运行的摄像头控制会停止，新会话在重置前不被接纳。操作员依次执行 `stop` → `reset-inputs` → `camera`，确认画面和操作者后再继续。
2. **同一会话重新选人：**跟踪编号增大时摄像头控制会停止；新人物信息已经记录，操作员检查后执行 `camera` 重新启用。较旧的跟踪编号不会使控制切回旧人物。
3. **普通短暂丢点：**保持同一会话发送缺点帧，C++ 根据各杆的有效数据时间执行保持和回中；不要自行重复旧坐标来刷新有效时间。

以上控制命令通过项目现有控制入口执行；适配器不自动发送启用命令。相机与 C++ 必须处于同一台板子的同一网络命名空间。本机 UDP 示例不代表已经完成跨电脑或跨板传输。

## 先在 Ubuntu 做软件联调

以下均在 `shadow_play` 工程目录中执行。测试代码不访问摄像头、DPU 或电机。

```bash
python3 -m unittest discover -s tests -p 'test_follow_sender.py' -v
```

生成模拟九点数据，输出为 C++ 已支持的录制格式：

```bash
python3 integrations/follow/pose_sender.py --jsonl --seconds 3 > build-linux/follow_demo.jsonl
./build-linux/shadow_show --mode camera --seconds 4 --replay build-linux/follow_demo.jsonl --output build-linux/follow_demo.csv
```

要验证本机 UDP，可在第一个终端运行：

```bash
./build-linux/shadow_show --mode camera --realtime --listen 56000 --seconds 10 --output build-linux/follow_udp.csv
```

在第二个终端运行：

```bash
python3 integrations/follow/pose_sender.py --seconds 3 --port 56000
```

这些命令使用模拟标定和 CSV 电机后端，只验证软件链路。输出文件必须使用尚不存在的名称。模拟器自身为了生成 30 Hz 演示数据而等待；实际 `publish` 内部没有等待、睡眠或后台发送线程。

实物联调时，队员二负责把此调用合入最新 FOLLOW 并提供真实数据；你负责 C++ 映射、协议和参数；硬件队友负责把最终轴命令接到真实电机后端，并标定每根杆对应云台的机械方向和允许范围。
