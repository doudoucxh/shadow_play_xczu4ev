#!/usr/bin/env python3
"""Read-only USB host/UVC diagnostics. Never changes drivers or boot files."""
import glob
import gzip
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'integrations/follow'))
from usb_camera import usb_devices


def probe():
    status = {}
    for path in glob.glob('/proc/device-tree/*/usb*@*'):
        node = Path(path)
        status[str(node)] = ((node/'status').read_bytes().rstrip(b'\0').decode()
                             if (node/'status').exists() else 'okay')
    config = ''
    if Path('/proc/config.gz').exists():
        with gzip.open('/proc/config.gz', 'rt') as stream:
            config = stream.read()
    flags = ('CONFIG_USB_XHCI_HCD', 'CONFIG_USB_DWC3', 'CONFIG_USB_DWC3_XILINX',
             'CONFIG_USB_VIDEO_CLASS', 'CONFIG_VIDEO_V4L2')
    enabled = {key: next((s.split('=',1)[1] for s in config.splitlines() if s.startswith(key+'=')),
                         'not enabled/unknown') for key in flags}
    devices = usb_devices()
    report = dict(usb_controllers=status, kernel=enabled, video_devices=devices,
                  usb_bus_entries=sorted(p.name for p in Path('/sys/bus/usb/devices').glob('*')))
    for device in devices:
        try:
            result = subprocess.run(['v4l2-ctl', '-d', device['device'], '--list-formats-ext'],
                                    capture_output=True, text=True, timeout=10)
            device['formats'] = result.stdout
            device['format_query_error'] = result.stderr
        except (OSError, subprocess.TimeoutExpired) as exc:
            device['format_query_error'] = str(exc)
    report['ready_for_capture_test'] = bool(devices)
    return report


if __name__ == '__main__':
    report = probe()
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report['ready_for_capture_test'] else 2)
