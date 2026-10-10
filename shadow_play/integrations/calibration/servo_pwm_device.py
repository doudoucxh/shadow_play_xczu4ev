"""Register driver for hardware/servo_pwm/servo_pwm_axi.v, not a generic PWM driver.

Construction is read-only. Call only after loading and verifying this project's
image. Outputs are enabled solely by explicit commissioning/arm operations.
"""
import mmap
import os
import time
from mmio32 import WordAccess

BASE = 0xA0030000
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
    def __init__(self, registers):
        self.reg = registers
        if self.reg.read(0) != 0x53503130:
            raise ValueError('SP10 peripheral not present')

    def status(self):
        return {'identity':'SP10','period_us':self.reg.read(0x28),
                'clock_hz':self.reg.read(0x2c),'enabled_mask':self.reg.read(8),
                'armed':bool(self.reg.read(0x10)), 'faults':self.reg.read(0x0c),
                'sequence':self.reg.read(0x20),'pending':bool(self.reg.read(0x24)),
                'pulse_us':[self.reg.read(0x80+4*i) for i in range(10)],
                'position_feedback':None}

    def off(self):
        self.reg.write(0x0c,0)
        state=self.status()
        if state['armed'] or state['enabled_mask'] or state['pending']:
            raise RuntimeError('OFF readback mismatch')
        return state

    def kick(self):
        if self.reg.read(0x10):
            self.reg.write(0x1c,0x4b49434b)

    def commit(self, pulses, mask, allow_arm=False):
        if len(pulses)!=10 or type(mask) is not int or not 0<=mask<1024:
            raise ValueError('Expected ten pulses and a ten-bit enable mask')
        if any(type(v) is not int or not 500<=v<=2500 for v in pulses):
            raise ValueError('All pulse widths must be integer microseconds in 500..2500')
        before=self.status()
        if before['pending']:
            raise RuntimeError('Previous commit is still pending; do not retry motion')
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
        deadline=time.monotonic()+0.12
        while time.monotonic()<deadline:
            after=self.status()
            if after['faults'] or not after['armed']:
                raise RuntimeError('PWM fault during commit; resynchronization required')
            if after['sequence']==expected and not after['pending']:
                if after['pulse_us']!=pulses or after['enabled_mask']!=mask:
                    raise RuntimeError('PWM adopted-state readback mismatch')
                return after
            time.sleep(.002)
        raise TimeoutError('PWM commit result unknown; command must not be retried automatically')


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
