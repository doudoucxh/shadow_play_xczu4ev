#!/usr/bin/env bash
set -euo pipefail
mount_dir="$HOME/vmware-shared"
mkdir -p "$mount_dir"
if ! mountpoint -q "$mount_dir"; then
    vmhgfs-fuse .host:/ "$mount_dir"
fi
findmnt "$mount_dir"
