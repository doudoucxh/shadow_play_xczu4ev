"""Register driver for hardware/servo_pwm/servo_pwm_axi.v, not a generic PWM driver.

Construction is read-only. Call only after loading and verifying this project's
image. Outputs are enabled solely by explicit commissioning/arm operations.
"""
import mmap
import os
from pathlib import Path
import time
from mmio32 import WordAccess

BASE = 0xA0030000
MOTION_INHIBIT = '/run/shadow-pwm-motion-inhibit'
PERSISTENT_MOTION_INHIBIT = Path(__file__).with_name('.motion-inhibit')
STATUS_READ_ATTEMPTS = 4
PINS = ('D14','D15','F13','G13','G14','G15','J14','E13','E14','E15')
IDS = tuple('servo_{:02d}_{}'.format(i+1, pin) for i, pin in enumerate(PINS))


class Registers:
    def __init__(self, verified_marker='/run/shadow-pwm-loaded.json'):
        import json
        from pathlib import Path
        import fcntl
        marker = json.loads(Path(verified_marker).read_text())
        if marker.get('register_base') != BASE or marker.get('image_kind') != 'servo10_vision':
            raise ValueError('PWM image has not been explicitly loaded for this boot')
        self.lock = open('/run/shadow-pwm.lock','a')
        fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.fd = os.open('/dev/mem', os.O_RDWR | os.O_SYNC)
        self.memory = mmap.mmap(self.fd,4096,mmap.MAP_SHARED,mmap.PROT_READ|mmap.PROT_WRITE,offset=BASE)
        try:
            self.words = WordAccess(self.memory)
        except Exception:
            self.memory.close(); os.close(self.fd); self.lock.close()
            raise
        if self.read(0) != 0x53503130 or self.read(4) != 1 or self.read(0x28) != 20000:
            self.close(); raise ValueError('Wrong PWM register identity/version/period')

    def read(self, offset):
        return self.words.read(offset)

    def write(self, offset, value):
        self.words.write(offset,value)

    def close(self):
        self.words.close()
        self.memory.close(); os.close(self.fd); self.lock.close()


class PwmDevice:
    def __init__(self, registers, *, motion_inhibit_paths=None):
        self.reg = registers
        self.motion_inhibit_paths = tuple((MOTION_INHIBIT, PERSISTENT_MOTION_INHIBIT)
                                          if motion_inhibit_paths is None else motion_inhibit_paths)
        if not self.motion_inhibit_paths:
            raise ValueError('Motion inhibit paths must not be empty')
        if self.reg.read(0) != 0x53503130:
            raise ValueError('SP10 peripheral not present')

    def status(self):
        # Frame adoption changes mask, pulses, pending and sequence together,
        # but separate AXI reads are not a snapshot. OFF/watchdog also change
        # control state without incrementing sequence. Retry reads only.
        def control():
            return (self.reg.read(8), self.reg.read(0x10),
                    self.reg.read(0x0c), self.reg.read(0x24))
        for _ in range(STATUS_READ_ATTEMPTS):
            sequence_before = self.reg.read(0x20)
            before = control()
            period = self.reg.read(0x28); clock_hz = self.reg.read(0x2c)
            pulses = [self.reg.read(0x80+4*i) for i in range(10)]
            after = control()
            sequence_after = self.reg.read(0x20)
            if sequence_before == sequence_after and before == after:
                return {'identity':'SP10','period_us':period,'clock_hz':clock_hz,
                        'enabled_mask':after[0],'armed':bool(after[1]),'faults':after[2],
                        'sequence':sequence_after,'pending':bool(after[3]),
                        'pulse_us':pulses,'position_feedback':None}
        raise RuntimeError('PWM status changed during bounded read-only snapshot; '
                           'sequence_before={}, sequence_after={}, control_before={}, '
                           'control_after={}'.format(sequence_before, sequence_after, before, after))

    def _check_motion_allowed(self):
        for path in self.motion_inhibit_paths:
            try:
                os.stat(path)
            except FileNotFoundError:
                continue
            raise RuntimeError('PWM motion inhibited by '+str(path)+'; status and OFF remain available')

    def off(self):
        """Immediate emergency stop; may truncate a pulse already high."""
        self.reg.write(0x0c,0)
        state=self.status()
        if state['armed'] or state['enabled_mask'] or state['pending']:
            raise RuntimeError('OFF readback mismatch')
        return state

    def stop_after_frame(self):
        """Normal stop: adopt mask zero at a frame boundary, then disarm.

        This disable-only path works with incident locks present. It never arms
        or changes active pulse widths. Any uncertain state falls back to OFF;
        it must never retry a commit or attempt to recover motion.
        """
        try:
            before = self.status()
            if before['pending'] or before['faults']:
                raise RuntimeError('Cannot drain uncertain/faulted PWM state')
            if not before['armed'] or not before['enabled_mask']:
                return self.off()
            pulses = before['pulse_us']
            if any(type(v) is not int or not 500 <= v <= 2500 for v in pulses):
                raise RuntimeError('Invalid active pulse readback during stop')
            # Do not call commit(): recovery subclasses deliberately restrict
            # it to their motion plan. These writes can only disable outputs.
            for i, value in enumerate(pulses):
                self.reg.write(0x40+4*i, value)
            self.reg.write(0x14, 0)
            self.reg.write(0x18, 0x434f4d54)
            expected = (before['sequence']+1) & 0xffffffff
            deadline = time.monotonic()+.12
            while time.monotonic() < deadline:
                after = self.status()
                if after['faults'] or not after['armed']:
                    raise RuntimeError('PWM stopped unexpectedly while draining frame')
                if after['sequence'] == expected and not after['pending']:
                    if after['enabled_mask'] or after['pulse_us'] != pulses:
                        raise RuntimeError('Frame stop adopted-state mismatch')
                    return self.off()
                if after['sequence'] not in (before['sequence'], expected):
                    raise RuntimeError('Unexpected sequence while draining frame')
                time.sleep(.002)
            raise TimeoutError('Frame stop adoption unknown; falling back to immediate OFF')
        except BaseException:
            self.off()
            raise

    def kick(self):
        if self.reg.read(0x10):
            self.reg.write(0x1c,0x4b49434b)

    def commit(self, pulses, mask, allow_arm=False):
        if len(pulses)!=10 or type(mask) is not int or not 0<=mask<1024:
            raise ValueError('Expected ten pulses and a ten-bit enable mask')
        if any(type(v) is not int or not 500<=v<=2500 for v in pulses):
            raise ValueError('All pulse widths must be integer microseconds in 500..2500')
        self._check_motion_allowed()
        before=self.status()
        if before['pending']:
            raise RuntimeError('Previous commit is still pending; do not retry motion')
        # Check again after the read-only snapshot, immediately before writes.
        self._check_motion_allowed()
        if not before['armed']:
            if not allow_arm:
                raise RuntimeError('Explicit per-channel commissioning is required before motion')
            self.reg.write(0x10,0x41524d31)
        elif before['faults']:
            raise RuntimeError('PWM fault: inspect, turn outputs off, and explicitly reinitialize')
        for i,value in enumerate(pulses):
            self.reg.write(0x40+4*i,value)
        self.reg.write(0x14,mask)
        self.reg.write(0x18,0x434f4d54)
        expected=(before['sequence']+1)&0xffffffff
        expected_state={'sequence':expected,'enabled_mask':mask,'pulse_us':pulses}
        after=before
        deadline=time.monotonic()+0.12
        while time.monotonic()<deadline:
            try:
                after=self.status()
            except RuntimeError as error:
                raise RuntimeError('PWM commit readback failed; expected={}, last_observed={}; {}'.format(
                    expected_state,after,error)) from error
            if after['faults'] or not after['armed']:
                raise RuntimeError('PWM fault during commit; resynchronization required; expected={}, observed={}'.format(
                    expected_state,after))
            if after['sequence']==expected and not after['pending']:
                if after['pulse_us']!=pulses or after['enabled_mask']!=mask:
                    raise RuntimeError('PWM adopted-state readback mismatch; expected={}, observed={}'.format(
                        expected_state,after))
                return after
            time.sleep(.002)
        raise TimeoutError('PWM commit result unknown; command must not be retried automatically; '
                           'expected={}, last_observed={}'.format(expected_state,after))


class CaptureDriver:
    def __init__(self, config, device):
        self.config=config;self.device=device
        specs={a['id']:a for a in config['axes']}
        if set(specs)!=set(IDS) or any(a['unit']!='us' for a in specs.values()):
            raise ValueError('Real config must match the verified ten servo IDs and microsecond units')
        if any(s.get('controllable') for s in config['slides']):
            raise ValueError('This driver never controls slides')
        self.specs=specs

    def read_state(self):
        import copy
        state=self.device.status()
        if not state['armed'] or state['enabled_mask']!=1023 or state['faults'] or state['pending']:
            raise RuntimeError('All ten servos must have an explicitly initialized, known adopted command')
        return {'adopted':[{'axis_id':name,'value':state['pulse_us'][i],'unit':'us'} for i,name in enumerate(IDS)],
                'slides':copy.deepcopy(self.config['slides']),'feedback':None}

    def apply_targets(self, axes, slides):
        if slides:
            raise ValueError('Slide motion is disabled')
        current=self.read_state()
        values={a['axis_id']:a for a in axes}
        if len(values)!=len(axes) or set(values)!=set(IDS):
            raise ValueError('Complete unique servo group required')
        pulses=[];changed=0
        for i,name in enumerate(IDS):
            value=values[name];spec=self.specs[name];v=value['value']
            if value['unit']!='us' or type(v) not in (int,float) or not spec['min']<=v<=spec['max']:
                raise ValueError('Unverified pulse or wrong unit for '+name)
            adopted=int(round(v));prior=current['adopted'][i]['value']
            if not spec['min']<=adopted<=spec['max'] or abs(adopted-prior)>spec['max_step']:
                raise ValueError('Pulse exceeds commissioned limit or maximum step: '+name)
            changed+=adopted!=prior;pulses.append(adopted)
        if changed>1:
            raise ValueError('Servo-only commissioning permits one changed channel per command')
        if changed:
            self.device.commit(pulses,1023)
        return self.read_state()
