# Vitis AI 3.0 conversion

The Vivado 2022.2 design uses `DPUCZDX8G v4.1`, so use a Vitis AI 3.0
PyTorch container. Do not compile only the wrist model: both commands below
process `pose_baseline_v2` and `pose_wrist_v2`.

Mount the original source read-only at `/workspace/pytorch_work` and this
release directory at `/workspace/release`, then run:

```bash
cd /workspace/release/vitis_ai
python quantize_models.py --mode calib --output /workspace/release/models/int8
python quantize_models.py --mode test  --output /workspace/release/models/int8
bash compile_xmodels.sh \
  /workspace/release/hardware/arch_b4096.json \
  /workspace/release/models/int8
```

Copy both compiled `.xmodel` files, `decoder/arm_chain_ranker.npz`, and
`runtime/arm_chain_dpu.py` to the target filesystem. The ranker and temporal
logic execute on the Cortex-A53; the two V2 convolutional networks execute on
the same B4096 DPU core in sequence.
