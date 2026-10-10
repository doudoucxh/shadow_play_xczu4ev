# 双 V2 模型 ARM-CHAIN DPU 部署包

本目录冻结了已经通过摄像头验证的完整推理链，不是单独替换腕部模型：

1. `pose_baseline_v2` 在 DPU 上推理，提供头、肩、髋及基础热图；
2. `pose_wrist_v2` 在同一 DPU 上顺序推理，提供腕部专项热图；
3. Cortex-A53 运行 `arm_chain_ranker.npz` 和 `arm_chain_dpu.py`，完成左右臂候选联合选择、肘部排他、前臂长度约束、时序跟踪、速度裁剪及 DOWN 约束。

关键点顺序固定为 `head, left_shoulder, right_shoulder, left_elbow, right_elbow, left_wrist, right_wrist, left_hip, right_hip`。

## 已完成的验证

- 原始 371 张验证集：肘 PCK@12px 90.78%，腕 PCK@12px 81.28%，整链同时正确 77.09%。
- 两个 FP32 ONNX 与原始 PyTorch 的最大绝对误差分别为 `5.16e-6`、`7.27e-6`。
- 板端 NumPy 解码器与原始 PyTorch 解码器选择结果完全一致。
- Vivado 2022.2 的 B4096 DPU 工程布局布线后 WNS 为 `+0.786 ns`，DRC 0 error；硬件产物位于 `hardware/`。其中 `system_wrapper_dpu_b4096.bit` 是时序通过的配置文件，`Shadow_ultra_dpu_b4096.xsa` 是从 Vivado 工程源数据库单独导出的 Vitis 硬件描述（包含 TopModuleName/HwDb，不内嵌 bitstream）。

## 生成两个 DPU xmodel

Vitis IDE 不包含 Vitis AI 量化器和编译器。请在 Vitis AI 3.0 PyTorch Linux 容器内按照 `vitis_ai/run_vitis_ai_3.md` 执行；必须生成并复制两个 xmodel，不能只转换腕部模型。

## 板端运行

目标系统需要 Vitis AI 3.0 的 XIR/VART、Python 3、NumPy 和 OpenCV，并且摄像头应暴露为 V4L2 设备或可由 OpenCV 读取的视频源：

```bash
python3 runtime/arm_chain_dpu.py \
  --baseline-xmodel models/int8/compiled_b4096/pose_baseline_v2/pose_baseline_v2.xmodel \
  --wrist-xmodel models/int8/compiled_b4096/pose_wrist_v2/pose_wrist_v2.xmodel \
  --arm-decoder decoder/arm_chain_ranker.npz \
  --camera /dev/video0 \
  --temporal-weight 0.35 \
  --min-forearm-ratio 0.45 \
  --down-pose-weight 0.5
```

正常画面左上角显示 `ARM-CHAIN`；双臂下垂约束激活时显示 `ARM-CHAIN+DOWN`。

### 当前工程的板端接口状态

当前 `vitis_workspace` 只有 `standalone_domain` 裸机域；OV5640 由裸机程序配置，姿态支路通过 `axi_vdma_pose` 写 DDR，并没有 Linux V4L2 设备。VART/DPU 板端执行需要 Linux，因此在实板验收前还必须提供一个带 Vitis AI 3.0 Runtime 的 Linux/PetaLinux 镜像，并完成以下两种摄像头接入方式之一：

- 为 OV5640 + AXI VDMA 媒体链补齐设备树和 Linux 驱动，使其成为 `/dev/video*`；
- 在 Linux 用户态映射专用 VDMA 帧缓冲，并把帧传给运行脚本。

仅安装 Windows 版 Vitis 2022.2 不会安装 `pytorch_nndct`、`vai_c_xir` 或板端 VART，因此不能在当前 Windows 环境中生成最终 INT8 xmodel，也不能完成实板七组动作验收。

`manifest.json` 记录原始权重、代码快照、导出模型和硬件文件的 SHA-256。原始训练权重未被覆盖或修改。
