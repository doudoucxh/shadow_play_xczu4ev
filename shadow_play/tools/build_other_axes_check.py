"""Install the requested one-axis diagnostic service; never start it."""
import argparse
from pathlib import Path
import build_v20_first_direction as package

RELEASE='other-axes-check-20261019'
LARGER_RELEASE='other-axes-40us-20261019'
OPPOSITE_RELEASE='other-axes-direction-20261019'
EXTENDED_RELEASE='other-axes-56us-20261019'
RECHECK_RELEASE='ten-axes-recheck-20261019'
REWIRE_RELEASE='rewired-axes-20261019'
DEST=Path('/run/media/mmcblk0p2/piying')/RELEASE
NAMES=('other_axes_check.py','initial_pose_model.py','v20_first_direction.py','servo_pwm_device.py','mmio32.py','libservo_mmio32.so')
NOTICE=b'Ordinary motion inhibited; only the explicitly requested finite single-axis checks.\n'

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['build','install'])
    p.add_argument('archive',type=Path);p.add_argument('--sha256')
    group=p.add_mutually_exclusive_group();group.add_argument('--larger-amplitude',action='store_true');group.add_argument('--opposite-direction',action='store_true');group.add_argument('--extended-56us',action='store_true');group.add_argument('--operator-recheck',action='store_true');group.add_argument('--rewired-recheck',action='store_true');a=p.parse_args()
    release=REWIRE_RELEASE if a.rewired_recheck else RECHECK_RELEASE if a.operator_recheck else EXTENDED_RELEASE if a.extended_56us else OPPOSITE_RELEASE if a.opposite_direction else LARGER_RELEASE if a.larger_amplitude else RELEASE
    if a.mode=='build':package.build(a.archive,release=release,names=NAMES,inhibit_notice=NOTICE)
    else:package.install(a.archive,a.sha256,release=release,names=NAMES,dest=DEST.parent/release)
