"""Enable USB0 after booting the reviewed MPSoC-P4 USB FSBL.

USB only. No raw MMIO, boot-file changes, FPGA loading, or motor commands.
Requires already-initialized pins/clocks/resets: refuses the old FSBL.
"""
import argparse
import hashlib
from pathlib import Path
import platform
import time

HASHES = {
    'prepare.dtbo': '37dd213519389c0fa69a51e20e938260b70535960265da7674a2dbecfb4a77af',
    'start.dtbo': 'ffe61864ef835512d897bc3e2718a7bdfbde6dcb82660e011ae8978288d1db3d',
}
DT = Path('/proc/device-tree')
OVERLAYS = Path('/sys/kernel/config/device-tree/overlays')
PM = Path('/sys/kernel/debug/zynqmp-firmware/pm')


def query(command):
    # Only the read-only queries used below are allowed.
    if command.split()[0] not in ('pm_reset_get_status', 'pm_pinctrl_get_function'):
        raise ValueError('Only firmware status queries are permitted')
    PM.write_text(command+'\n')
    return PM.read_text().strip()


def check_fsbl(wrapper_ready=False):
    if platform.release() != '5.15.36-xilinx-v2022.2':
        raise RuntimeError('Kernel has not been reviewed for this overlay')
    # PMU may assert core reset while the unused USB power domain is idle.
    # Binding the wrapper requests the domain; PMU then pulses/releases it.
    # APB + hibernation resets and ULPI must already be initialized by FSBL.
    for reset in ((1059, 1061, 1063) if wrapper_ready else (1061, 1063)):
        if query('pm_reset_get_status %d' % reset) != 'Reset status: 0':
            raise RuntimeError('USB0 is still in reset; boot the USB FSBL first')
    gpio = query('pm_pinctrl_get_function 24')
    functions = {query('pm_pinctrl_get_function %d' % pin) for pin in range(52, 64)}
    if functions != {'Current set function for the pin: 43'} or gpio in functions:
        raise RuntimeError('USB0 ULPI pins are not initialized by the FSBL')


def apply(directory, filename, name):
    data = (directory/filename).read_bytes()
    if hashlib.sha256(data).hexdigest() != HASHES[filename]:
        raise ValueError('Unreviewed overlay: '+filename)
    target = OVERLAYS/name
    if target.exists():
        raise RuntimeError('Overlay already exists; inspect state before retrying: '+name)
    target.mkdir()
    (target/'dtbo').write_bytes(data)
    if (target/'status').read_text().strip() != 'applied':
        raise RuntimeError('Overlay failed: '+name)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--overlay-dir', type=Path, required=True)
    p.add_argument('--apply', action='store_true', help='Enable USB after all preflight checks')
    args = p.parse_args()
    check_fsbl()
    # Validate both blobs before any mutation.
    for name, expected in HASHES.items():
        if hashlib.sha256((args.overlay_dir/name).read_bytes()).hexdigest() != expected:
            raise ValueError('Overlay checksum mismatch: '+name)
    if not args.apply:
        print('USB_FSBL_PREFLIGHT_OK; pass --apply to enable Linux USB0')
        return
    if list(Path('/sys/bus/usb/devices').iterdir()):
        raise RuntimeError('USB is already active; no reconfiguration performed')
    for path in ('axi/usb0@ff9d0000', 'axi/usb0@ff9d0000/usb@fe200000'):
        if (DT/path/'status').read_bytes() != b'disabled\0':
            raise RuntimeError('Expected the original disabled USB device tree')
    apply(args.overlay_dir, 'prepare.dtbo', 'piying-usb2-prepare')
    if not Path('/sys/bus/platform/devices/ff9d0000.usb0/driver').is_symlink():
        raise RuntimeError('USB wrapper driver did not bind; inspect dmesg, do not start DWC3')
    check_fsbl(wrapper_ready=True)
    apply(args.overlay_dir, 'start.dtbo', 'piying-usb2-start')
    deadline = time.monotonic()+10
    while time.monotonic() < deadline:
        if Path('/sys/bus/usb/devices/usb1').exists():
            print('USB_HOST_READY')
            return
        time.sleep(.2)
    raise RuntimeError('USB host did not enumerate; inspect dmesg')


if __name__ == '__main__':
    main()
