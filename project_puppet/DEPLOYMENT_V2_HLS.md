# 最新 V2 模型 HLS INT8 部署

本流程的唯一模型入口是仓库根目录 `best.pt`。导出器只接受 `TinyUpperPoseNetV2`，会严格校验完整 state-dict、`1×3×144×256` 输入、`1×9×36×64` 输出、24/32/48 通道、14 次 HLS 提交及缓冲区上限。旧权重路径和旧人工审核 schema 均不参与部署。

当前 checkpoint SHA256：

```text
01c852378a963ddec52b457d88bc4af2e03aef57847533afd5213d4a6855eb1c
```

## 1. 工具链验收

完整 Vitis 2022.2 安装到 `D:\xilinx` 后执行：

```powershell
& .\ultral_xczu4ev\scripts\check_vitis_2022_2.ps1
```

输出会保存在 `deploy\logs\vitis_2022_2_preflight.txt`。脚本优先使用 `XILINX_VITIS`，否则检查 `D:\xilinx\Vitis\2022.2`。

## 2. 用现有固件采集 200 个真实 ROI

板卡上电并连接 JTAG、UART、OV5640 和 HDMI；启动 Hardware Server 后，在摄像头前依次完成展开、交叉、抬手、遮挡、侧身、远近和不同光照：

```powershell
# 此时工作区中的旧 ELF 仍可用于采集；先启动它，不要先重编。
& '.\ultral_xczu4ev\program_and_run.bat'

& 'D:\xilinx\Vitis\2022.2\bin\xsct.bat' `
  '.\ultral_xczu4ev\scripts\capture_calibration_inputs.tcl' `
  '.\deploy\board_calibration' 200
```

采集器兼容旧的 v6 结果结构和新的 v7 原子快照。每个 `.input.bin` 必须恰好 110592 字节，内容为板端送入 HLS 核的 `256×144 BGR` ROI。

## 3. 导出、量化并重编 A53 ELF

```powershell
& .\deploy_latest_model.ps1 -CalibrationDir '.\deploy\board_calibration'
```

导出物包括：

- `pose_model_weights.h`：确定性 Conv+BN 融合后的浮点回退参数；
- `pose_model_int8_weights.h`：uint8 激活、逐输出通道 int8 权重、int32 bias、u16 multiplier/right-shift；
- `pose_model_int8_weights.json`：量化范围、层序、比例和校准样本哈希；
- `deploy\artifacts\pose_model_int8.npz`：主机定点仿真参数；
- `deploy\artifacts\model_manifest.json`：checkpoint 与所有生成物 SHA256。

本阶段只重编 A53 ELF；继续使用已经通过时序的 `system_wrapper.bit`、XSA 和 FSBL，不重新实现 PL。

重编前可用现有 Vitis HLS 单样本 C-sim 复核 Python 定点模型与 HLS 算术：

```powershell
& '.\.venv\Scripts\python.exe' '.\tools\prepare_hls_csim_sample.py' `
  '.\Photo427_2\IMG00201.BMP' '.\deploy\csim'
& 'D:\xilinx\Vitis_HLS\2022.2\bin\vitis_hls.bat' -f `
  '.\ultral_xczu4ev\hls\pose_cnn_accel\run_model_csim.tcl'
& '.\.venv\Scripts\python.exe' '.\tools\verify_hls_csim_output.py' `
  '.\deploy\csim\python_heatmap.bin' '.\deploy\csim\hls_heatmap.bin' `
  --output '.\deploy\reports\hls_csim_consistency.json'
```

## 4. JTAG 启动

```powershell
& .\deploy_latest_model.ps1 -CalibrationDir '.\deploy\board_calibration' -SkipBuild -Program
```

下载脚本依次初始化 PS/DDR、下载 bitstream、释放 PS–PL 隔离和复位、探测视频 VDMA、姿态 VDMA 与 HLS AXI、下载并启动 A53 应用。UART 的正常周期状态必须包含：

```text
backend=PL layers=14 failed_layer=0
model_sha256=01c852378a963ddec52b457d88bc4af2e03aef57847533afd5213d4a6855eb1c
```

验证构建默认 `POSE_VALIDATION_BUILD=1`。任一 PL 层失败时不会静默切到 PS；UART 报告失败层，HDMI 保持上一帧成功结果。

## 5. 采集 50 个独立原子快照并验证

校准姿态采完后换一组动作，采集至少 50 帧：

```powershell
& 'D:\xilinx\Vitis\2022.2\bin\xsct.bat' `
  '.\ultral_xczu4ev\scripts\capture_pose_snapshots.tcl' `
  '.\deploy\board_validation' 50

& '.\.venv\Scripts\python.exe' '.\tools\validate_pose_consistency.py' `
  --validation-dir '.\deploy\board_validation' --validation-count 50 `
  --validation-offset 0 --fpga-dir '.\deploy\board_validation'
```

v7 固件在同一提交中保存 `0x02300000` 输入和 `0x02400000` 的 `36×64×16` INT8 heatmap。主机在读取前后复核快照序号。

验收门限：FP32→INT8 九点平均坐标差不超过 2 输入像素，至少 98% 的点不超过 8 输入像素；Python 定点→FPGA heatmap 必须逐字节一致、解码坐标一致，并且全部为 PL、14 层完成、失败层为 0。

报告输出到 `deploy\reports`。该报告只称“部署一致性验证”；未使用人工真值，因此不输出或宣称真实 PCK。

## 6. 实时十分钟检查

持续运行十分钟并保存 UART 日志。人工确认摄像头/HDMI 无中断、撕裂和颜色通道错误，左右肢体不交换，抬手、交叉、快速移动和静止时骨架合理。统计脚本应基于 UART/快照记录输出 PL 推理耗时和端到端 FPS 的中位数、P95；任何 HLS 超时、CPU 回退或帧计数停滞都判为失败。

`Photo427_2` 只能用于主机侧冒烟测试，必须使用 `--calibration-kind provisional_images` 明确标记，不能替代最终 200 帧板端 ROI 校准和 50 帧实机一致性验收。
