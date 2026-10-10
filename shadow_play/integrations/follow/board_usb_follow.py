#!/usr/bin/env python3
"""USB camera -> existing DPU Pose9/FOLLOW -> HDMI and camera-v2 UDP.

Never starts a motor backend. Use --no-send for image/inference-only validation.
"""
from board_follow_with_sender import main

if __name__ == '__main__':
    main(default_camera='usb')
