"""Transmit-only text on the two isolated rail UARTs; default offline.

The driver RX wires must be disconnected before this test. This diagnostic
never sends motor protocol, reads RX FIFO, resets UART or writes PWM registers.
RX flags are reported separately; they do not establish the state of TX.
"""
import argparse
from collections import deque
import hashlib
import json
import mmap
import os
from pathlib import Path
import time
import uuid
import signal
import threading

IMAGE_SHA='ea680d88d2d149157490ebbe27b253b3814d6d2df17aeebb477047bb4bc81e90'
PORTS={
    'person':dict(base=0xA0040000,tx_pin='F15',rx_pin='H13'),
    'tiger':dict(base=0xA0050000,tx_pin='H14',rx_pin='L13'),
}
TEXT={'person':b'PERSON 12345\r\n','tiger':b'TIGER 12345\r\n'}
COUNT=5


class TextPort:
    def __init__(self,registers,name,*,repeat=False,clock=time.monotonic,sleep=time.sleep):
        if name not in TEXT:raise ValueError('Only the two fixed port labels')
        self.reg=registers;self.name=name;self.clock=clock;self.sleep=sleep
        self.lines=0;self.failed=False;self.repeat=repeat;self.diagnostics=deque(maxlen=32)

    def status(self):
        s=self.reg.read(8)
        if type(s) is not int or not 0<=s<=255 or s&0x10:
            raise RuntimeError('Unexpected status or interrupt-owned UART')
        return s

    def idle(self):
        s=self.status()
        if not s&4 or s&8:raise RuntimeError('TX FIFO not empty; no retry or reset')
        return s

    def send_line(self):
        if self.failed or (not self.repeat and self.lines>=COUNT):raise RuntimeError('Diagnostic exhausted or failed')
        queued=0;before=None
        try:
            before=self.idle();quiet=self.clock()+.02
            while self.clock()<quiet:
                self.idle();self.sleep(.0005)
            # Both fixed lines fit entirely in the 16-byte FIFO checked empty.
            line=TEXT[self.name]
            if len(line)>16:raise ValueError('Fixed line exceeds empty FIFO capacity')
            for value in line:self.reg.write(4,value);queued+=1
            deadline=self.clock()+.1
            while True:
                after=self.status()
                if after&4 and not after&8:break
                if self.clock()>=deadline:raise TimeoutError('TX drain timeout; no resend')
                self.sleep(.0002)
            self.lines+=1
            row=dict(port=self.name,line_number=self.lines,text=line.decode('ascii'),hex=line.hex(),
                bytes_queued=queued,status_before=before,status_after=after,
                rx_flags_before=before&0xE3,rx_flags_after=after&0xE3,
                tx_fifo_drained=True,wire_received_verified=False)
            self.diagnostics.append(row);return row
        except BaseException:
            self.failed=True
            self.diagnostics.append(dict(port=self.name,line_number=self.lines+1,
                bytes_queued=queued,status_before=before,failed=True,wire_received_verified=False))
            raise


def stopped(state,sequence):
    if (type(sequence) is not int or sequence<0 or state['sequence']!=sequence
            or any(state[k] for k in ('armed','enabled_mask','faults','pending'))):
        raise RuntimeError('Fresh matching clean OFF state required')


def validate_image(marker,boot):
    rail=marker.get('rail_uart',{})
    if (marker.get('boot_id')!=boot or marker.get('sha256')!=IMAGE_SHA
            or marker.get('design_checks')!='SERVO_IMAGE_DESIGN_CHECKS_PASS'
            or rail.get('design_checks')!='RAIL_UART_DESIGN_CHECKS_PASS'
            or rail.get('ports')!=PORTS or rail.get('baud')!=115200 or rail.get('format')!='8N1'):
        raise RuntimeError('Reviewed standard dual-UART image required; no reload performed')


def run_continuous(ports,check,stop,report,*,clock=time.monotonic):
    """One line per port per second, with prompt stop and no catch-up bursts."""
    while not stop.is_set():
        check();started=clock()
        for port in ports.values():
            if stop.is_set():return
            check();port.send_line()
        report(True)
        deadline=started+1
        while not stop.is_set() and clock()<deadline:
            check();stop.wait(min(.1,max(0,deadline-clock())))


def save_status(path,row):
    temporary=path.with_name(path.name+'.tmp')
    temporary.write_text(json.dumps(row)+'\n')
    temporary.replace(path)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--execute-text',action='store_true')
    p.add_argument('--motor-rx-disconnected-confirmed',action='store_true')
    p.add_argument('--ttl-3v3-confirmed',action='store_true')
    p.add_argument('--boot-id');p.add_argument('--expected-sequence',type=int)
    p.add_argument('--request-id')
    p.add_argument('--continuous',action='store_true')
    a=p.parse_args()
    if not a.execute_text:
        print('UART_TEXT_OFFLINE '+json.dumps(dict(ports=PORTS,text={k:v.decode('ascii') for k,v in TEXT.items()},
            count_per_port=None if a.continuous else COUNT,continuous=a.continuous,
            baud=115200,format='8N1',motor_motion=False)));return
    if not a.motor_rx_disconnected_confirmed or not a.ttl_3v3_confirmed:
        raise RuntimeError('Actual motor RX disconnection and 3.3V TTL confirmation required')
    if (not a.boot_id or a.expected_sequence is None or not a.request_id
            or uuid.UUID(hex=a.request_id).hex!=a.request_id):
        raise ValueError('Fresh boot, OFF sequence and unique request ID required')
    import fcntl
    from contextlib import ExitStack
    from mmio32 import WordAccess
    from servo_pwm_device import Registers,PwmDevice
    boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    if boot!=a.boot_id:raise RuntimeError('Boot changed; no transmit')
    marker=json.loads(Path('/run/shadow-pwm-loaded.json').read_text());validate_image(marker,boot)
    with ExitStack() as stack:
        lock=stack.enter_context(Path('/run/shadow-rail-uart.lock').open('a'))
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        reg=Registers();stack.callback(reg.close);pwm=PwmDevice(reg)
        before=pwm.status();stopped(before,a.expected_sequence)
        used=Path('/run/uart-tx-text-'+a.request_id+'.used')
        with used.open('x') as out:out.write(json.dumps(dict(boot_id=boot,sequence=a.expected_sequence))+'\n')
        ports={}
        for name,info in PORTS.items():
            fd=os.open('/dev/mem',os.O_RDWR|os.O_SYNC);stack.callback(os.close,fd)
            mem=stack.enter_context(mmap.mmap(fd,4096,mmap.MAP_SHARED,mmap.PROT_READ|mmap.PROT_WRITE,offset=info['base']))
            words=WordAccess(mem);stack.callback(words.close);ports[name]=TextPort(words,name,repeat=a.continuous)
        for port in ports.values():port.idle()
        stop=threading.Event();failure=None
        def stopping(signum,frame):stop.set()
        if a.continuous:
            signal.signal(signal.SIGTERM,stopping);signal.signal(signal.SIGINT,stopping)
        marker_raw=Path('/run/shadow-pwm-loaded.json').read_bytes()
        incident=Path('/run/shadow-pwm-motion-inhibit')
        lock_sha=hashlib.sha256(incident.read_bytes()).hexdigest()
        def check():
            if pwm.status()!=before:raise RuntimeError('PWM changed; stop text test')
            if (Path('/run/shadow-pwm-loaded.json').read_bytes()!=marker_raw
                    or hashlib.sha256(incident.read_bytes()).hexdigest()!=lock_sha):
                raise RuntimeError('Image marker or incident lock changed; stop text test')
        def report(active):
            row=dict(request_id=a.request_id,pid=os.getpid(),boot_id=boot,
                updated_monotonic=time.monotonic(),active=active,state=pwm.status(),
                lines={n:v.lines for n,v in ports.items()},error=failure,
                image_sha256=IMAGE_SHA,incident_lock_sha256=lock_sha,
                interval_seconds=1,wire_received_verified=False,motor_motion=False)
            save_status(Path('/run/uart-text-stream-20261020.json'),row)
            rounds=min(row['lines'].values())
            if not active or rounds==1 or rounds%60==0:
                print('UART_TEXT_STREAM '+json.dumps(row),flush=True)
        try:
            if a.continuous:run_continuous(ports,check,stop,report)
            else:
                for i in range(COUNT):
                    check()
                    for name,port in ports.items():
                        print('UART_TEXT_SENT '+json.dumps(port.send_line()),flush=True)
                    if i+1<COUNT:time.sleep(1)
        except BaseException as error:
            failure=type(error).__name__+': '+str(error)
            raise
        finally:
            after=pwm.status()
            if a.continuous:report(False)
            print('UART_TEXT_FINAL '+json.dumps(dict(state=after,pwm_unchanged=after==before,
                lines={n:v.lines for n,v in ports.items()},motor_motion=False,wire_received_verified=False)),flush=True)
        if after!=before:raise RuntimeError('PWM state changed during diagnostic')


if __name__=='__main__':main()
