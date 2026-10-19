"""Explicit inspected watchdog reset with every PWM channel disabled.

No COMMIT, pulse width, enable-mask, image, or incident-lock writes are made.
This operation cannot restore a physical pose or authorize a motion route.
"""
import hashlib
from pathlib import Path

from v20_first_direction import IMAGE


def reset_disabled_watchdog(device, *, expected_state, boot_id, marker,
                            onsite_inspected, used_path):
    if onsite_inspected is not True or marker.get('boot_id') != boot_id or marker.get('sha256') != IMAGE:
        raise ValueError('Current verified image and onsite inspection required')
    before = device.status()
    if (before != expected_state or before.get('identity') != 'SP10'
            or before.get('period_us') != 20000 or before.get('clock_hz') != 100000000
            or before.get('armed') is not False or type(before.get('enabled_mask')) is not int
            or before['enabled_mask'] != 0 or before.get('pending') is not False
            or type(before.get('faults')) is not int or before['faults'] != 2
            or type(before.get('sequence')) is not int
            or not 0 <= before['sequence'] <= 0xffffffff
            or len(before.get('pulse_us', [])) != 10
            or any(type(v) is not int or not 500 <= v <= 2500 for v in before['pulse_us'])):
        raise RuntimeError('Only the exact inspected disabled watchdog fault is recoverable')

    def locks():
        # Missing lock evidence is not permission to recover.
        return tuple(hashlib.sha256(Path(p).read_bytes()).hexdigest()
                     for p in device.motion_inhibit_paths)

    hashes = locks()
    if device.status() != before:
        raise RuntimeError('State changed before reset')
    with Path(used_path).open('x', encoding='ascii') as file:
        file.write(boot_id + ':' + str(before['sequence']))
    try:
        device.off()  # RTL clears staged and queued masks as well as active mask.
        if device.status() != before or locks() != hashes:
            raise RuntimeError('State or incident locks changed before reset')
        device.reg.write(0x10, 0x41524d31)  # ARM clears the latched fault, with mask zero.
        during = device.status()
        expected_during = dict(before, armed=True, faults=0)
        if during != expected_during:
            raise RuntimeError('Unexpected state during disabled reset')
    finally:
        device.off()
    after = device.status()
    if after != dict(before, faults=0) or locks() != hashes:
        raise RuntimeError('Disabled reset verification failed')
    return dict(before=before, after=after, during=during,
                incident_lock_sha256=list(hashes), pwm_channels_enabled=False,
                position_feedback=None)
