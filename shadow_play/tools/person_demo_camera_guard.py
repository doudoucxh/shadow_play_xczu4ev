#!/usr/bin/env python3
"""Private dual-view recording and expiring freshness lease for the one-shot demo."""
from concurrent.futures import ThreadPoolExecutor
import io
import json
from pathlib import Path
import sys
import time
import urllib.request
from PIL import Image


def record(folder,base='http://192.168.45.1:8765'):
    folder.mkdir(parents=True,exist_ok=False)
    last={};good={c:time.monotonic() for c in ('front','top')};advancing=set()
    def fetch(camera):
        with urllib.request.urlopen(base+'/'+camera+'.jpg',timeout=.65) as r:
            data=r.read();age=int(r.headers['X-Frame-Age-Ms']);fid=r.headers['X-Frame-Id']
        if not fid or not 0<=age<=800:raise RuntimeError('Frame missing or stale')
        with Image.open(io.BytesIO(data)) as im:
            im.load()
            if im.format!='JPEG':raise RuntimeError('Expected JPEG')
        stamp=time.time_ns();name=camera+'_'+str(stamp)+'.jpg';(folder/name).write_bytes(data)
        return dict(camera=camera,file=name,host_unix_ns=stamp,frame_id=fid,age_ms=age)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool,(folder/'frames.jsonl').open('x',encoding='utf-8') as log:
            until=time.monotonic()+110
            while time.monotonic()<until and not (folder/'finish.request').exists():
                futures={c:pool.submit(fetch,c) for c in ('front','top')}
                for c,f in futures.items():
                    try:
                        row=f.result()
                        if row['frame_id']!=last.get(c):
                            if c in last:advancing.add(c)
                            last[c]=row['frame_id'];good[c]=time.monotonic()
                    except Exception as error:row=dict(camera=c,error=str(error),host_unix_ns=time.time_ns())
                    log.write(json.dumps(row)+'\n');log.flush()
                    if time.monotonic()-good[c]>1.2:raise RuntimeError('No fresh decoded '+c+' frame')
                if len(advancing)==2 and all(time.monotonic()-t<.8 for t in good.values()):
                    temp=folder/'lease.tmp';temp.write_text(json.dumps({'unix_ms':time.time_ns()//1000000}),encoding='ascii')
                    temp.replace(folder/'lease.json')
                time.sleep(.15)
            if not (folder/'finish.request').exists():raise RuntimeError('Recorder duration expired')
    except BaseException as error:
        (folder/'guard.error').write_text(str(error),encoding='utf-8');raise


if __name__=='__main__':record(Path(sys.argv[1]))
