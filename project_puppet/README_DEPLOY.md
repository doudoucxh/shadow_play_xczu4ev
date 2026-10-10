# README_DEPLOY.md（旧 DPU 交接说明，已停止作为部署入口）

> 当前部署只使用根目录 `best.pt` 的 V2 HLS INT8 裸机路线。请以 `DEPLOYMENT_V2_HLS.md` 为准；本文中的旧模型路径、DPU 流程和历史 PCK 只保留作背景，不得用于本次生成或验收。

# 皮影戏人体姿态识别模型 —— DPU 部署交接说明

## 1. 项目目标

本项目用于 FPGA 创新设计大赛，目标是利用人体姿态识别结果操控皮影戏。

整体流程：

```text
摄像头图像
    ↓
人体姿态识别模型
    ↓
输出 9 个上半身关键点
    ↓
关键点滤波 / 关节角计算
    ↓
映射为皮影动作
    ↓
舵机 / 执行机构控制
```

后续部署目标：

```text
PyTorch FP32
    ↓
ONNX
    ↓
INT8 量化
    ↓
DPU 编译
    ↓
Ultral / FPGA SoC 板端运行
```

---

## 2. 当前推荐部署模型

当前推荐使用：

```text
Data_004_baseline_40\best.pt
```

建议在部署包中重命名为：

```text
upper_pose_v2_baseline40.pt
```

不要使用此前 Data_003 模型、专项 loss 实验模型或 baseline_45 作为默认部署版本。

当前已知验证结果：

```text
PCK@12px Overall ≈ 87.36%
PCK@20px Overall ≈ 92.14%
```

PCK@20px 下主要肢体指标：

```text
left_elbow   ≈ 92.66%
right_elbow  ≈ 91.28%
left_wrist   ≈ 73.61%
right_wrist  ≈ 74.02%
```

---

## 3. 网络结构

网络结构文件：

```text
pose_model/model.py
```

部署时使用：

```python
make_pose_model("v2")
```

对应模型类：

```python
TinyUpperPoseNetV2
```

模型主体主要包含：

```text
Conv2d
BatchNorm2d
ReLU
Depthwise Conv 3×3
Pointwise Conv 1×1
Residual Add
Nearest-neighbor Upsample
```

V2 结构大致为：

```text
Input
  ↓
Stem Conv
  ↓
High-resolution branch
  ↓
High refine blocks
  ↓
Low-resolution context branch
  ↓
Context projection
  ↓
Nearest-neighbor ×2
  ↓
High + Context
  ↓
Refine blocks
  ↓
1×1 Head
  ↓
9-channel heatmap
```

DPU 编译阶段重点确认：

```text
1. Depthwise convolution（groups = in_channels）
2. nearest-neighbor interpolate
3. element-wise add
```

是否能够完整下沉到目标 DPU。具体支持情况与目标 DPU 架构及 Vitis AI / 编译器版本有关。

---

## 4. 模型输入

模型输入：

```text
NCHW
[1, 3, 144, 256]
```

即：

```text
Batch   = 1
Channel = 3
Height  = 144
Width   = 256
```

输入图像按 RGB 处理。

PyTorch 导出阶段输入类型：

```text
float32
```

INT8 DPU 部署时由量化流程决定最终输入格式。

---

## 5. 模型输出

模型输出：

```text
[1, 9, 36, 64]
```

含义：

```text
Batch          = 1
Keypoints      = 9
Heatmap Height = 36
Heatmap Width  = 64
```

每个关键点对应一张：

```text
36 × 64
```

heatmap，输出为 heatmap logits。

建议 DPU 只负责网络前向，argmax、坐标恢复、滤波和关节角计算放 ARM / CPU 端。

---

## 6. 9 个关键点通道顺序

输出通道固定为：

```text
0  head
1  left_shoulder
2  right_shoulder
3  left_elbow
4  right_elbow
5  left_wrist
6  right_wrist
7  left_hip
8  right_hip
```

注意：

```text
left / right 表示“人体自身的左 / 右”
```

不是观察者画面中的左右。

部署端不能改变通道顺序。

---

## 7. Heatmap 解码

基础解码方式：

```text
每个关键点通道：
36 × 64 heatmap
    ↓
argmax
    ↓
得到 heatmap 坐标 (x_hm, y_hm)
```

当前 heatmap 相对于输入图像缩小约 4 倍。

可动态恢复输入坐标：

```python
scale_x = input_width / heatmap_width
scale_y = input_height / heatmap_height

x_input = x_hm * scale_x
y_input = y_hm * scale_y
```

当前：

```text
scale_x = 256 / 64 = 4
scale_y = 144 / 36 = 4
```

---

## 8. 精度指标

建议部署前后至少比较：

```text
PyTorch FP32 PCK@12
PyTorch FP32 PCK@20

ONNX PCK@12
ONNX PCK@20

DPU INT8 PCK@12
DPU INT8 PCK@20
```

这样可以判断：

```text
FP32 → ONNX → INT8 → DPU
```

每一步是否产生精度损失。

---

## 9. 预处理要求

部署端预处理必须与训练 / PC 推理保持一致。

重点确认：

```text
1. RGB / BGR 通道顺序
2. Resize 方法
3. ROI / Crop 方式
4. 输入尺寸 256 × 144
5. 归一化方式
6. 是否存在图像上下裁边
```

不要仅根据模型输入尺寸自行重写预处理。

建议部署人员参考当前 V2 导出与一致性验证实现：

```text
export_pose_hls.py
validate_pose_consistency.py
```

以及项目中的 PC 端参考推理逻辑。

如果板端精度明显低于 PC，优先排查：

```text
RGB/BGR
归一化
Resize
Crop / ROI
INT8 scale / zero-point
输入 tensor 排布
输出 tensor 排布
```

---

## 10. 推荐板端处理流程

建议 DPU 侧：

```text
RGB Image
    ↓
Preprocess
    ↓
DPU
    ↓
9 × 36 × 64 heatmap
```

ARM / CPU 侧：

```text
Heatmap
    ↓
Argmax
    ↓
坐标恢复
    ↓
时序滤波
    ↓
骨骼向量
    ↓
肩 / 肘关节角度
    ↓
动作映射
    ↓
舵机 / 执行机构控制
```

不建议直接使用 wrist 的绝对 XY 坐标控制舵机。

更推荐通过：

```text
Shoulder → Elbow → Wrist
```

计算骨骼方向与关节夹角，再映射到皮影关节。

---

## 11. 时序滤波建议

逐帧姿态预测直接控制舵机会产生抖动。

建议优先尝试 EMA：

```python
filtered_x = alpha * current_x + (1.0 - alpha) * previous_x
filtered_y = alpha * current_y + (1.0 - alpha) * previous_y
```

推荐初始范围：

```text
alpha = 0.3 ~ 0.5
```

也可以测试：

```text
3~5 帧中值滤波
```

该部分计算量很小，建议放 ARM 端。

---

## 12. INT8 量化建议

优先尝试 PTQ（Post Training Quantization）。

建议准备：

```text
100 ~ 300 张
```

有代表性的量化校准图片。

覆盖：

```text
普通站姿
双手展开
双手交叉
手臂抬起
手腕遮挡
侧身
不同距离
不同衣服
不同光照
```

不要只选择容易识别的样本。

如果 PTQ 后精度明显下降，再考虑 QAT。

---

## 13. DPU 部署验证

部署过程中建议保留三套结果：

```text
1. PyTorch FP32
2. ONNX
3. DPU INT8
```

对相同图片比较 9 个关键点坐标。

建议记录：

```text
输出 shape
输出通道顺序
单张图片 9 点坐标
PCK@12
PCK@20
FPS
DPU inference latency
CPU postprocess latency
end-to-end latency
```

理想结果：

```text
PyTorch ≈ ONNX ≈ DPU INT8
```

INT8 可有小幅误差，但不应出现明显系统性坐标偏移。

---

## 14. ONNX 导出注意事项

导出前：

```python
model.eval()
```

第一版建议固定输入：

```text
[1, 3, 144, 256]
```

不建议第一版就使用动态 shape。

导出后至少确认：

```text
PyTorch output shape = [1, 9, 36, 64]
ONNX output shape    = [1, 9, 36, 64]
```

并用完全相同的输入数据比较输出和关键点坐标。

---

## 15. 推荐部署交付包

```text
Pose_DPU_Deployment/
│
├── model/
│   ├── upper_pose_v2_baseline40.pt
│   ├── model.py
│   └── config.py
│
├── reference/
│   ├── export_pose_hls.py
│   ├── validate_pose_consistency.py
│   └── prepare_hls_csim_sample.py
│
├── calibration/
│   ├── image_001.*
│   ├── image_002.*
│   └── ...
│
├── README_DEPLOY.md
│
└── requirements.txt
```

最少必须交付：

```text
upper_pose_v2_baseline40.pt
model.py
预处理说明
关键点输出顺序
输入 / 输出 shape
```

---

## 16. 当前版本标识

```text
Architecture:
TinyUpperPoseNetV2

Architecture ID:
v2

Input:
1 × 3 × 144 × 256

Output:
1 × 9 × 36 × 64

Keypoints:
9

Recommended checkpoint:
Data_004_baseline_40 / best.pt

Primary deployment metrics:
PCK@12px
PCK@20px
```

---

## 17. 交接原则

部署阶段优先保证：

```text
1. PC 与板端预处理一致
2. PyTorch 与 ONNX 输出一致
3. ONNX 与 INT8 / DPU 输出一致
4. 网络尽可能完整运行在 DPU
5. ARM 只承担轻量后处理
6. 控制端使用滤波后的关节角，而不是直接使用原始 XY
```

目前建议优先完成：

```text
PT → ONNX → INT8 → DPU → 实时控制闭环
```

完成板端闭环后，再根据 DPU 实测精度、延迟和资源占用决定是否继续修改模型。
