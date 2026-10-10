#!/bin/bash
set -euo pipefail
release=/mnt/d/xilinx_project/ZYNQ_project/project_puppet/project_puppet/deploy/yolo_pose9
project=/home/wzh/work/shadow_dpu_petalinux
tools_dir="$project/build/tmp/work/zynqmp_generic-xilinx-linux/u-boot-xlnx/v2021.01-xilinx-v2022.2+gitAUTOINC+b31476685d-r0/build/tools"
export PATH="$project/build/tmp/work/x86_64-linux/qemu-xilinx-helper-native/1.0-r1/recipe-sysroot-native/usr/bin:$PATH"
out="$release/sd_candidate"
mkdir -p "$out" "$release/rollback" "$release/integration/evidence"
# This reset-enabled image preserves the previously fixed DPU driver and runtime.
base=/mnt/c/WZH_File/codex_camera_ila_20260921/production_output/image.ub
sha256sum "$base" | grep -q '^e558d92862fabc91fcb9a9c705a76d6161bd34835264812b9e1e8c9fbde1ad97 '
cp "$base" "$release/rollback/arm_chain_reset_image.ub"
cd "$out"
"$tools_dir/dumpimage" -T flat_dt -p 0 -o kernel.gz "$base" >/dev/null
"$tools_dir/dumpimage" -T flat_dt -p 1 -o system.dtb "$base" >/dev/null
"$tools_dir/dumpimage" -T flat_dt -p 2 -o original-rootfs.cpio.gz "$base" >/dev/null
python3 "$release/integration/assemble_rootfs.py" original-rootfs.cpio.gz "$release" rootfs.cpio.gz > "$release/integration/evidence/rootfs_changes.json"
cp "$release/integration/image.its" image.its
"$tools_dir/mkimage" -f image.its image.ub > "$release/integration/evidence/fit_image.txt"
"$tools_dir/dumpimage" -T flat_dt -p 0 -o verify-kernel.gz image.ub >/dev/null
"$tools_dir/dumpimage" -T flat_dt -p 1 -o verify-system.dtb image.ub >/dev/null
"$tools_dir/dumpimage" -T flat_dt -p 2 -o verify-rootfs.cpio.gz image.ub >/dev/null
cmp kernel.gz verify-kernel.gz
cmp system.dtb verify-system.dtb
cmp rootfs.cpio.gz verify-rootfs.cpio.gz
gzip -dc verify-rootfs.cpio.gz | cpio -i --to-stdout opt/shadow/yolo_pose9/model/yolo_pose9_b4096.xmodel > verify-model.xmodel
cmp verify-model.xmodel "$release/model/yolo_pose9_b4096.xmodel"
gzip -dc verify-rootfs.cpio.gz | cpio -i --to-stdout opt/shadow/yolo_pose9/runtime/runtime.py > verify-runtime.py
cmp verify-runtime.py "$release/runtime/runtime.py"
cp "$project/images/linux/boot.scr" boot.scr
for name in shadow_hw_init.h ov5640_init.c; do cp "$project/project-spec/meta-user/recipes-apps/shadow-arm-chain/files/$name" "$release/integration/source/$name"; done
sha256sum image.ub boot.scr
