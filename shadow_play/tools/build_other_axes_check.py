"""Install the requested one-axis diagnostic service; never start it."""
import argparse
from pathlib import Path
import build_v20_first_direction as package

RELEASE='other-axes-check-20261019'
DEST=Path('/run/media/mmcblk0p2/piying')/RELEASE
NAMES=('other_axes_check.py','initial_pose_model.py','v20_first_direction.py','servo_pwm_device.py','mmio32.py','libservo_mmio32.so')
NOTICE=b'Ordinary motion inhibited; only the explicitly requested finite single-axis checks.\n'

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['build','install'])
    p.add_argument('archive',type=Path);p.add_argument('--sha256');a=p.parse_args()
    if a.mode=='build':package.build(a.archive,release=RELEASE,names=NAMES,inhibit_notice=NOTICE)
    else:package.install(a.archive,a.sha256,release=RELEASE,names=NAMES,dest=DEST)
