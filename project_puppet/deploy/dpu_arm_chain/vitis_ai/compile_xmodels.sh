#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 <arch.json> <quantized-dir>" >&2
  exit 2
fi

arch_json="$(realpath "$1")"
quant_dir="$(realpath "$2")"
output_dir="${quant_dir}/compiled_b4096"
mkdir -p "${output_dir}"

for model_name in pose_baseline_v2 pose_wrist_v2; do
  source_xmodel="$(find "${quant_dir}/${model_name}" -maxdepth 1 -name '*.xmodel' -print -quit)"
  if [[ -z "${source_xmodel}" ]]; then
    echo "missing quantized xmodel for ${model_name}" >&2
    exit 1
  fi
  vai_c_xir \
    --xmodel "${source_xmodel}" \
    --arch "${arch_json}" \
    --output_dir "${output_dir}/${model_name}" \
    --net_name "${model_name}"
done

find "${output_dir}" -name '*.xmodel' -print
