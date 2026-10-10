#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
raw="${1:-release/raw}"
out="${2:-release/int8}"
mkdir -p "$out"
docker run --rm --network none --entrypoint /bin/bash \
  -e RAW_DIR="$raw" -e OUT_DIR="$out" \
  -v "$PWD:/workspace" -w /workspace \
  xilinx/vitis-ai-pytorch-cpu:ubuntu2004-3.0.0.106 -lc '
    source /opt/vitis_ai/conda/etc/profile.d/conda.sh
    conda activate vitis-ai-pytorch
    python quantize.py --raw "$RAW_DIR" --dataset dataset --output "$OUT_DIR" --mode calib --samples 128
    python quantize.py --raw "$RAW_DIR" --dataset dataset --output "$OUT_DIR" --mode test --samples 1
    vai_c_xir -x "$OUT_DIR/RawPose_int.xmodel" -a arch.json -o "$OUT_DIR/compiled" -n yolo_pose9
    python inspect_xmodel.py "$OUT_DIR/compiled/yolo_pose9.xmodel" --output "$OUT_DIR/compiled/graph_audit.json"
    python evaluate_quantized.py --raw "$RAW_DIR" --quantized "$OUT_DIR" --dataset dataset --split val --output evaluation/int8_val
    python evaluate_quantized.py --raw "$RAW_DIR" --quantized "$OUT_DIR" --dataset dataset --split test --output evaluation/int8_test
  ' > "$out/vitis_ai.log" 2>&1
