"""One current fixed-V20 head component with two fresh camera leases; default read-only."""
import argparse
import base64
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sys
import threading
import time
import uuid

ROOT=Path(__file__).resolve().parents[2]
CAL=ROOT/'shadow_play/integrations/calibration'
sys.path.insert(0,str(CAL))
from fixed_v20_probe import BOARD,BOOT,IMAGE,REFERENCE,REFERENCE_SHA,SCHEMA,CLOSE_SCHEMA,CLOSE_BOARD,route,validate_plan
from fixed_v20_probe import SUPPORT_SCHEMA,SUPPORT_BOARD,SUPPORT_REF,SUPPORT_SHA
from v20_first_direction import MIDPOINT,PREFIX,digest
from run_v20_first_direction import parse_event,valid_reference,FreshCamera
from run_v20_head_lift import PhoneCamera
from servo_center_session import await_prompt

LIB=BOARD+'/integrations/calibration'
FILES=('fixed_v20_probe.py','other_axes_check.py','initial_pose_model.py','v20_first_direction.py','servo_pwm_device.py','mmio32.py','libservo_mmio32.so')
WORK=ROOT/'.review_work/fixed-v20-return-20261019'


def prior_reference(channel,closeup=False,supported=False):
    if supported:
        if channel!=8:raise ValueError('Supported mode changes only axis 8')
        raw=(ROOT/'shadow_play/config/fixed_v20_supported_reference_20261019.json').read_bytes()
        if hashlib.sha256(raw).hexdigest()!=SUPPORT_SHA:raise RuntimeError('Supported reference changed')
        ref=json.loads(raw)
        return dict(route_complete=True,state=ref['state'],boot_id=ref['boot_id'],
                    source_log_path=SUPPORT_REF,board_log_sha256=SUPPORT_SHA)
    if closeup:
        if channel!=8:raise ValueError('Only head axis 8 for the new close view')
        previous=json.loads((WORK/'axis-8/result.json').read_text(encoding='utf-8'))
        return dict(route_complete=previous['result']['route_complete'],state=previous['result']['state'],
                    boot_id=previous['plan']['boot_id'],source_log_path=previous['audit']['board_log'],
                    board_log_sha256=previous['audit']['board_log_sha256'])
    if channel==7:
        p=ROOT/'shadow_play/config/fixed_v20_start_reference_20261019.json'
        raw=p.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=REFERENCE_SHA:raise RuntimeError('Operator reference changed')
        ref=json.loads(raw)
        return dict(route_complete=True,state=ref['state'],boot_id=ref['boot_id'],
                    source_log_path=REFERENCE,board_log_sha256=REFERENCE_SHA)
    previous=json.loads((WORK/'axis-7/result.json').read_text(encoding='utf-8'))
    return dict(route_complete=previous['result']['route_complete'],state=previous['result']['state'],
                boot_id=previous['plan']['boot_id'],source_log_path=previous['audit']['board_log'],
                board_log_sha256=previous['audit']['board_log_sha256'])


class DualCamera:
    def __init__(self):
        self.root=ROOT/'camera_liveview/output'
        self.session=json.loads((self.root/'current.json').read_text(encoding='utf-8-sig'))['directory']
        self.front=FreshCamera(self.root);self.rear=PhoneCamera()

    def sample(self,destination=None):
        if json.loads((self.root/'current.json').read_text(encoding='utf-8-sig'))['directory']!=self.session:
            raise RuntimeError('Sony session changed; stop')
        front=None if destination is None else destination.with_name(destination.stem+'-front.jpg')
        rear=None if destination is None else destination.with_name(destination.stem+'-rear.jpg')
        return dict(front=self.front.sample(front),rear=self.rear.sample(rear))


def run(channel,output,execute=False,port_name='COM17',closeup=False,supported=False):
    import serial
    if type(channel) is not int or channel not in (7,8):raise ValueError('Only head axes 7/8')
    if closeup and channel!=8:raise ValueError('Only axis 8 for the close view')
    if supported and (channel!=8 or closeup):raise ValueError('Supported mode changes only axis 8')
    output.mkdir(parents=True,exist_ok=False)
    stop=threading.Event();worker=None;started=False;final=audit=None
    port=serial.Serial(None,115200,timeout=.05,write_timeout=.5)
    port.dtr=port.rts=False;port.port=port_name;pending=b''
    camera=DualCamera();captures=[];lock=threading.Lock()
    board=SUPPORT_BOARD if supported else CLOSE_BOARD if closeup else BOARD;lib=board+'/integrations/calibration'
    with (output/'serial.jsonl').open('x',encoding='utf-8') as log:
        def record(key,value):
            with lock:
                log.write(json.dumps(dict(utc=datetime.now(timezone.utc).isoformat(),**{key:value}))+'\n');log.flush()
        def send(value):
            if len(value)>3800:raise ValueError('Canonical command too long')
            record('send',value);port.write(value.encode('ascii'))
        def receive(test,seconds):
            nonlocal pending
            deadline=time.monotonic()+seconds
            while time.monotonic()<deadline:
                while b'\n' in pending:
                    line,pending=pending.split(b'\n',1)
                    result=test(line.strip().decode('utf-8','replace'))
                    if result is not None:return result
                raw=port.read(4096)
                if raw:pending+=raw;record('receive',raw.decode('utf-8','replace'))
            raise TimeoutError('No expected response; no retry')
        def python(code,prefix=''):
            data=base64.b64encode(code.encode('utf-8')).decode()
            send(prefix+"python3 -u -c \"import base64;exec(base64.b64decode('"+data+"'))\"\r")
        try:
            port.open();port.write(b'\r')
            if await_prompt(port,6,service='attended-initial-pose-v1')!='root':
                raise RuntimeError('Terminal owned by another session')
            send('stty -echo\r');time.sleep(.2);port.read_all()
            names=FILES if execute else ('servo_pwm_device.py','mmio32.py','libservo_mmio32.so')
            hashes={n:hashlib.sha256((CAL/n).read_bytes()).hexdigest() for n in names}
            python("import sys,json,hashlib;from pathlib import Path;p=Path('"+lib+"');h="+repr(hashes)+
                ";assert all(hashlib.sha256((p/n).read_bytes()).hexdigest()==v for n,v in h.items());"
                "sys.path.insert(0,str(p));from servo_pwm_device import Registers,PwmDevice;"
                "r=Registers();s=PwmDevice(r).status();r.close();"
                "print('OTHER_INSPECT '+json.dumps(dict(state=s,boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),"
                "marker=json.loads(Path('/run/shadow-pwm-loaded.json').read_text()))),flush=True)")
            inspected=receive(lambda s:json.loads(s.split('OTHER_INSPECT ',1)[1]) if 'OTHER_INSPECT ' in s else None,8)
            (output/'inspection.json').write_text(json.dumps(inspected,indent=2),encoding='utf-8')
            print('READ_ONLY '+json.dumps(inspected),flush=True)
            if not execute:return inspected
            valid_reference(inspected['state']);previous=prior_reference(channel,closeup,supported)
            if (not previous['route_complete'] or previous['state']['sequence']!=inspected['state']['sequence']
                or previous['state']['pulse_us']!=MIDPOINT or previous['boot_id']!=BOOT or inspected['boot_id']!=BOOT
                or inspected['marker'].get('boot_id')!=BOOT or inspected['marker'].get('sha256')!=IMAGE):
                raise RuntimeError('Current state differs from completed source')
            request=dict(request_id=uuid.uuid4().hex,
                user_request='Fixed-rail V20 real demonstration requested; current onsite midpoint confirmed',
                channel=channel,excursion_us=40,other_nine_disabled=True,
                camera_sources=['sony_front','phone_rear'],preparation_component_only=True,rails_moved=False)
            if closeup:request['user_request']='Phone adjusted to head mechanism; continue check explicitly requested'
            if supported:
                request.update(user_request='Operator reports axis 8 normal with all-ten center program and explicitly requests continuation',
                    other_nine_disabled=False,other_nine_held_at_midpoint=True,enabled_mask=1023)
            plan=dict(schema=SUPPORT_SCHEMA if supported else CLOSE_SCHEMA if closeup else SCHEMA,session_id=uuid.uuid4().hex,new_request_id=request['request_id'],boot_id=BOOT,
                channel=channel,expected_sequence=inspected['state']['sequence'],expected_pulse_us=MIDPOINT,
                route_sha256=digest(route(channel)),prior_log_path=previous['source_log_path'],
                prior_log_sha256=previous['board_log_sha256'],camera_required=True,onsite_observer=True,
                new_hardware_request=True,mechanism_visible=True)
            validate_plan(plan)
            captures.append(dict(stage='before',**camera.sample(output/'camera-before.jpg')))
            (output/'plan.json').write_text(json.dumps(plan,indent=2),encoding='utf-8')
            target=board+'/axis-'+str(channel)+'-'+plan['session_id']+'.json'
            data=base64.b64encode(json.dumps(plan).encode()).decode()
            python("import base64,os;f=open('"+target+"','xb');f.write(base64.b64decode('"+data+"'));f.close();"
                   "os.execv('/usr/bin/python3',['python3','-u','"+lib+"/fixed_v20_probe.py','"+target+"','--execute-one-axis-check'])",
                   prefix='PYTHONPATH='+lib+' ')
            ready=receive(parse_event,8)
            if ready.get('event')!='ready' or ready.get('session_id')!=plan['session_id']:
                raise RuntimeError('Ready response mismatch')
            valid_reference(ready['state'])
            if ready['state']['sequence']!=plan['expected_sequence']:raise RuntimeError('State changed before start')
            started=True;send(': # V20_BEGIN '+plan['session_id']+'\n')
            def leases():
                while not stop.wait(.3):
                    try:camera.sample();send(': # V20_LEASE '+plan['session_id']+'\n')
                    except BaseException as error:
                        record('lease_failure',type(error).__name__)
                        try:send(': # V20_STOP\n')
                        except Exception:pass
                        stop.set();return
            worker=threading.Thread(target=leases,daemon=True);worker.start()
            while audit is None:
                event=receive(parse_event,12);print(json.dumps(event),flush=True)
                if event.get('event')=='frame':
                    index=event['index']
                    captures.append(dict(stage='frame_'+str(index),**camera.sample(output/('camera-frame-'+str(index)+'.jpg'))))
                elif event.get('event')=='outputs_off':
                    final=event
                    if not final['route_complete']:break
                elif event.get('event')=='audit':audit=event
            result=dict(request=request,plan=plan,result=final,audit=audit,camera_captures=captures,
                        physical_motion_verified=False,observer_note=None)
            (output/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
            if final is None or not final['route_complete']:raise RuntimeError('Incomplete; no return or retry')
            valid_reference(final['state']);return result
        finally:
            stop.set()
            if worker is not None:worker.join(1)
            if port.is_open:
                try:
                    if started and final is None:
                        send(': # V20_STOP\n');time.sleep(.15);port.write(b'\x03');time.sleep(.2)
                    port.write(b'\r')
                    if await_prompt(port,4,service='attended-initial-pose-v1')=='root':port.write(b'stty echo\r')
                finally:port.close()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--channel',type=int,choices=(7,8),required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--port',default='COM17')
    p.add_argument('--execute-checked-axis',action='store_true')
    group=p.add_mutually_exclusive_group()
    group.add_argument('--head-closeup',action='store_true')
    group.add_argument('--supported-check',action='store_true')
    a=p.parse_args()
    run(a.channel,a.output,a.execute_checked_axis,a.port,a.head_closeup,a.supported_check)
