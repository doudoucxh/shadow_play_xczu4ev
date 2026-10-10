#!/bin/bash
set -euo pipefail
release="$(cd "$(dirname "$0")/.." && pwd)"
project=/home/wzh/work/shadow_dpu_petalinux
tools_dir="$project/build/tmp/work/zynqmp_generic-xilinx-linux/u-boot-xlnx/v2021.01-xilinx-v2022.2+gitAUTOINC+b31476685d-r0/build/tools"
export PATH="$project/build/tmp/work/x86_64-linux/qemu-xilinx-helper-native/1.0-r1/recipe-sysroot-native/usr/bin:$PATH"
out="$(mktemp -d /home/wzh/work/yolo_sd_verify.XXXXXX)"
echo "BUILD_DIR=$out"
cd "$out"
cp "$release/sd_candidate/kernel.gz" "$release/sd_candidate/system.dtb" .
python3 "$release/integration/assemble_rootfs.py" "$release/sd_candidate/original-rootfs.cpio.gz" "$release" rootfs.cpio.gz > "$release/integration/evidence/rootfs_changes.json"
cp "$release/integration/image.its" image.its
"$tools_dir/mkimage" -f image.its image.ub > "$release/integration/evidence/fit_image.txt"
for i in 0 1 2; do "$tools_dir/dumpimage" -T flat_dt -p "$i" -o "verify-$i" image.ub >/dev/null; done
cmp kernel.gz verify-0
cmp system.dtb verify-1
cmp rootfs.cpio.gz verify-2
for file in runtime/runtime.py runtime/graph_contract.py runtime/postprocess.py model/yolo_pose9_b4096.xmodel; do
 gzip -dc verify-2 | cpio -i --to-stdout "opt/shadow/yolo_pose9/$file" > verify-file
 cmp verify-file "$release/$file"
done
cp image.ub "$release/sd_candidate/image.ub"
cp "$project/images/linux/boot.scr" "$release/sd_candidate/boot.scr"
cp "$project/images/linux/boot.scr" "$release/rollback/boot.scr"
for file in shadow_hw_init.h ov5640_init.c; do cp "$project/project-spec/meta-user/recipes-apps/shadow-arm-chain/files/$file" "$release/integration/source/$file"; done
sha256sum "$release/sd_candidate/image.ub"
echo 'FINAL_FIT_AND_ALL_RUNTIME_FILES_VERIFIED'
