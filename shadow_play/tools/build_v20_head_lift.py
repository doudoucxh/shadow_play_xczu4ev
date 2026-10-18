"""Isolated axis-8 service installer. Never starts a service or moves hardware."""
import argparse
from pathlib import Path
import build_v20_first_direction as package

RELEASE = 'v20-head-lift-20261018'
DEST = Path('/run/media/mmcblk0p2/piying') / RELEASE
NAMES = ('v20_head_lift.py', 'v20_first_direction.py', 'servo_pwm_device.py',
                 'mmio32.py', 'libservo_mmio32.so')
NOTICE = b'Only the explicitly requested one-use axis-8 head-lift check; ordinary motion inhibited.\n'
PHONE_RELEASE = 'v20-head-lift-phone-20261019'

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['build', 'install'])
    parser.add_argument('archive', type=Path)
    parser.add_argument('--sha256')
    parser.add_argument('--phone-recheck', action='store_true')
    a = parser.parse_args()
    release = PHONE_RELEASE if a.phone_recheck else RELEASE
    dest = DEST.parent / release
    if a.mode == 'build': package.build(a.archive, release=release, names=NAMES, inhibit_notice=NOTICE)
    else: package.install(a.archive, a.sha256, release=release, names=NAMES, dest=dest)
