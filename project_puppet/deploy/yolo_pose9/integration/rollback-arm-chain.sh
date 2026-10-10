#!/bin/sh
set -eu
test "$(id -u)" = 0 || { echo 'Run as root'; exit 1; }
systemctl disable --now shadow-yolo-pose.service
systemctl enable --now shadow-arm-chain.service
systemctl --no-pager status shadow-arm-chain.service
