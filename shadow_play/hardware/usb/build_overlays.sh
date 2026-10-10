#!/bin/sh
# Usage: sh build_overlays.sh ORIGINAL_BOARD_DTB NEW_OUTPUT_DIRECTORY
set -eu
SOURCE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BASE=$1
OUT=$2
test -f "$BASE"
test ! -e "$OUT"
mkdir -p "$OUT"
dtc -@ -I dts -O dtb -o "$OUT/prepare.dtbo" "$SOURCE/mpsoc_p4_usb2_prepare.dts"
dtc -@ -I dts -O dtb -o "$OUT/start.dtbo" "$SOURCE/mpsoc_p4_usb2_start.dts"
dtc -@ -I dts -O dtb -o "$OUT/boot.dtbo" "$SOURCE/mpsoc_p4_usb2_boot.dts"
fdtoverlay -i "$BASE" -o "$OUT/reviewed-boot.dtb" "$OUT/boot.dtbo"
test "$(fdtget -t s "$OUT/reviewed-boot.dtb" /axi/usb0@ff9d0000 status)" = okay
test "$(fdtget -t s "$OUT/reviewed-boot.dtb" /axi/usb0@ff9d0000/usb@fe200000 status)" = okay
sha256sum "$OUT/prepare.dtbo" "$OUT/start.dtbo" "$OUT/boot.dtbo"
