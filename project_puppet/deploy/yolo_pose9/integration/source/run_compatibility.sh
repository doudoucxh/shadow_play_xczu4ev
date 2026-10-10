#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
docker run --rm --network none --entrypoint /bin/bash \
  -v "$PWD:/workspace" -w /workspace \
  xilinx/vitis-ai-pytorch-cpu:ubuntu2004-3.0.0.106 -lc '
    source /opt/vitis_ai/conda/etc/profile.d/conda.sh
    conda activate vitis-ai-pytorch
    python quantize.py --raw compatibility/raw --dataset dataset --output compatibility/quantized --mode calib --samples 8
    python quantize.py --raw compatibility/raw --dataset dataset --output compatibility/quantized --mode test --samples 1
    vai_c_xir -x compatibility/quantized/RawPose_int.xmodel -a arch.json -o compatibility/compiled -n pose9_compatibility
  ' > compatibility/vitis_ai.log 2>&1
