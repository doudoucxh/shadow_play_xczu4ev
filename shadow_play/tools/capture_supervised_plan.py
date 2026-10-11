#!/usr/bin/env python3
"""Record a finite attended board plan with two-camera freshness supervision.

Does not create motion plans or reload the FPGA. Stop on lost video/serial data;
never retry motion. Camera images are private local evidence, not Git content.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
import threading
import time
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parent))
from servo_center_session import await_prompt
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'integrations/calibration'))
from camera_bridge import check_jpeg


DEFAULT_BOARD_SCRIPT = '/tmp/supervised_capture_plan_20261011_v2.py'
MOTION_REVIEW = Path(__file__).resolve().parents[1] / 'config/servo_loaded_motion_stop.json'


def require_motion_review_clear(path=MOTION_REVIEW):
    """Fail closed before opening serial/cameras; no command-line override."""
    try:
        review = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        raise RuntimeError('Motion review record missing/unreadable; capture is blocked') from error
    if (not isinstance(review, dict) or review.get('schema_version') != 1 or
            review.get('active') is not False):
        raise RuntimeError('Loaded motion is stopped after puppet pulling; mechanical review and a verified start are required')


def validate_board_script(value):
    if not re.fullmatch(r'/tmp/[A-Za-z0-9_][A-Za-z0-9_.-]*\.py', value):
        raise argparse.ArgumentTypeError('Simple /tmp Python script path required')
    return value


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--board-plan',required=True)
    p.add_argument('--board-script',type=validate_board_script,default=DEFAULT_BOARD_SCRIPT)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--port',default='COM3')
    p.add_argument('--camera-base',default='http://192.168.45.1:8765')
    args=p.parse_args()
    require_motion_review_clear()
    if not re.fullmatch(r'/tmp/[A-Za-z0-9_.-]+\.json',args.board_plan):
        raise ValueError('Simple /tmp JSON plan required')
    import serial
    args.output.mkdir(parents=True,exist_ok=False)
    stop=threading.Event(); ready=threading.Event(); finish=threading.Event()
    guard={'reason':None}; label={'value':None}; current_lock=threading.Lock()

    def fetch(name):
        with current_lock: before=label['value']
        with urllib.request.urlopen(args.camera_base+'/'+name+'.jpg',timeout=.65) as r:
            data=check_jpeg(r.read()); age=int(r.headers['X-Frame-Age-Ms'])
            frame_id=r.headers['X-Frame-Id']
            if not frame_id or not 0<=age<=1200: raise ValueError('stale frame')
            with current_lock: after=label['value']
            ns=time.time_ns();filename=name+'_'+str(ns)+'.jpg'
            (args.output/filename).write_bytes(data)
            return dict(camera=name,frame_id=frame_id,age_ms=age,file=filename,
                        source_read_at=r.headers['X-Frame-Read-At'],host_unix_ns=ns,
                        label=before if before==after else None)

    def cameras():
        last={}; good={name:time.monotonic() for name in ('front','top')}
        initial=set()
        with ThreadPoolExecutor(max_workers=2) as pool,(args.output/'frames.jsonl').open('x',encoding='utf-8') as log:
            while not finish.is_set():
                for name,future in zip(('front','top'),[pool.submit(fetch,n) for n in ('front','top')]):
                    try:
                        row=future.result()
                        if row['frame_id']!=last.get(name):
                            if name in last: initial.add(name)
                            last[name]=row['frame_id'];good[name]=time.monotonic()
                    except Exception as error:
                        row=dict(camera=name,error=str(error),host_unix_ns=time.time_ns())
                    log.write(json.dumps(row)+'\n');log.flush()
                    if time.monotonic()-good[name]>1.2:
                        guard['reason']='Camera unavailable/frozen: '+name
                        stop.set();return
                if len(initial)==2:ready.set()
                finish.wait(.18)

    def guarded_cameras():
        try: cameras()
        except BaseException as error:
            guard['reason']='Camera recorder failed: '+str(error);stop.set()
    worker=threading.Thread(target=guarded_cameras,daemon=True);worker.start()
    port=None; started=False; off=False; completed=False
    try:
        if not ready.wait(4) or stop.is_set():raise RuntimeError(guard['reason'] or 'Two advancing camera streams required')
        port=serial.Serial(port=None,baudrate=115200,timeout=.05,write_timeout=.5)
        port.dtr=False;port.rts=False;port.port=args.port;port.open()
        port.write(b'\r')
        if await_prompt(port,service='finite-capture-plan')!='root':raise RuntimeError('Root shell required')
        port.write(b'stty -echo\r');time.sleep(.15);port.read_all()
        if stop.is_set():raise RuntimeError(guard['reason'])
        command=('PYTHONPATH=/run/media/mmcblk0p2/piying/servo-capture-20261008-r4/integrations/calibration '
                 'python3 -u '+args.board_script+' '+args.board_plan+
                 ' --execute --require-host-lease; echo PLAN_COMPLETE:$?; stty echo\r')
        port.write(command.encode('ascii'));started=True
        deadline=time.monotonic()+70;interrupted=False;last_lease=time.monotonic()
        with (args.output/'board.log').open('x',encoding='utf-8') as raw,(args.output/'events.jsonl').open('x',encoding='utf-8') as log:
            while time.monotonic()<deadline:
                if not worker.is_alive() and not finish.is_set():stop.set()
                if stop.is_set() and not interrupted:
                    port.write(b'\x03');interrupted=True;deadline=min(deadline,time.monotonic()+5)
                if not stop.is_set() and not off and time.monotonic()-last_lease>=.25:
                    # Also a harmless shell no-op if the finite program just exited.
                    port.write(b': # CAPTURE_LEASE\n');last_lease=time.monotonic()
                line=port.readline().decode('utf-8',errors='replace').strip()
                if not line:continue
                raw.write(line+'\n');raw.flush()
                if line.startswith('{"event":'):
                    row=json.loads(line);row['host_received_at']=datetime.now(timezone.utc).isoformat()
                    row['host_unix_ns']=time.time_ns();log.write(json.dumps(row)+'\n');log.flush()
                    with current_lock:label['value']=row.get('label') if row['event']=='sample_begin' else None
                    if row['event']=='outputs_off':
                        s=row['state'];off=s['enabled_mask']==0 and not s['armed'] and not s['pending']
                    print(json.dumps(row),flush=True)
                if line.startswith('PLAN_COMPLETE:'):
                    completed=line=='PLAN_COMPLETE:0';break
        if not off or not completed or stop.is_set():
            raise RuntimeError(guard['reason'] or 'Plan did not finish with confirmed OFF; inspect before another action')
        print('CAPTURE_COMPLETE_ALL_OUTPUTS_OFF',flush=True)
    finally:
        if port is not None and port.is_open:
            if started and not off:
                port.write(b'\x03');time.sleep(.3)
            port.close()
        finish.set();worker.join(timeout=3)
        (args.output/'capture_result.json').write_text(json.dumps(dict(
            completed=completed,outputs_off_confirmed=off,camera_guard_error=guard['reason']),indent=2),encoding='utf-8')


if __name__=='__main__':main()
