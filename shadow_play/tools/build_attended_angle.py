"""Package/install the standalone operator-selected angle service; never start it."""
import argparse
from pathlib import Path
import build_v20_first_direction as package

RELEASE='attended-angle-20261019'
DEST=Path('/run/media/mmcblk0p2/piying')/RELEASE
NAMES=('attended_angle_console.py','attended_center_console.py','manual_servo_console.py',
       'center_console.py','board_server.py','tcp_bridge.py','servo_pwm_device.py','mmio32.py','libservo_mmio32.so')
NOTICE=b'Ordinary choreography remains inhibited; explicit attended single-axis manual requests only.\n'

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['build','install'])
    p.add_argument('archive',type=Path);p.add_argument('--sha256');a=p.parse_args()
    if a.mode=='build':package.build(a.archive,release=RELEASE,names=NAMES,inhibit_notice=NOTICE)
    else:package.install(a.archive,a.sha256,release=RELEASE,names=NAMES,dest=DEST)
