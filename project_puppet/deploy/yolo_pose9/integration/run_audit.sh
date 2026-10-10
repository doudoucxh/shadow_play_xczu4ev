#!/bin/bash
set -euo pipefail
release="$(cd "$(dirname "$0")/.." && pwd)"
docker run --rm --network none --entrypoint /bin/bash -v "$release:/release" xilinx/vitis-ai-pytorch-cpu:ubuntu2004-3.0.0.106 -lc 'source /opt/vitis_ai/conda/etc/profile.d/conda.sh; conda activate vitis-ai-pytorch; python /release/integration/audit_graph.py /release/model/yolo_pose9_b4096.xmodel /release/integration/evidence/graph_contract.json'
