"""One B4096 CNN runner + A53 YOLO decode; full-resolution camera input."""
import argparse
import json
import mmap
import os
import struct
import time
from pathlib import Path
import cv2
import numpy as np
from postprocess import preprocess, decode
from graph_contract import validate_graph, EXPECTED_FINGERPRINT
import subprocess

EDGES=[(0,1),(0,2),(1,2),(1,3),(3,5),(2,4),(4,6),(1,7),(2,8),(7,8)]


class DpuModel:
    def __init__(self,path,size=384):
        import xir
        import vart
        self.graph=xir.Graph.deserialize(str(path))
        dpu=validate_graph(self.graph)
        self.runner=vart.Runner.create_runner(dpu,'run')
        ins=self.runner.get_input_tensors()
        self.outs=self.runner.get_output_tensors()
        if len(ins)!=1 or tuple(ins[0].dims)!=(1,size,size,3):
            raise ValueError('Expected one NHWC RGB input')
        if not ins[0].has_attr('fix_point') or str(ins[0].dtype).lower() not in ('xint8','int8'):
            raise ValueError('Expected INT8 input tensor')
        self.input_fix=ins[0].get_attr('fix_point')
        self.buffers=[np.empty(tuple(t.dims),np.int8) for t in self.outs]
        self.mapping={}
        for i,t in enumerate(self.outs):
            shape=tuple(t.dims)
            if len(shape)!=4 or shape[0]!=1 or shape[1]!=shape[2] or not t.has_attr('fix_point') or str(t.dtype).lower() not in ('xint8','int8'):
                raise ValueError(f'Unexpected output tensor {t.name}: {shape}')
            key=(shape[1],shape[3])
            if key in self.mapping: raise ValueError(f'Ambiguous tensor mapping {key}')
            self.mapping[key]=i
        self.order=[]
        for stride in (8,16,32):
            for channels in (64,1,27):
                self.order.append(self.mapping[(size//stride,channels)])
        if len(self.outs)!=9: raise ValueError('Expected nine raw prediction outputs')

    def __call__(self,x):
        if x.shape!=(1,3,384,384) or not np.isfinite(x).all() or x.min()<0 or x.max()>1:
            raise ValueError('Expected finite RGB [0,1] tensor at 384x384')
        value=np.ascontiguousarray(np.clip(np.rint(x.transpose(0,2,3,1)*(2.0**self.input_fix)),-128,127).astype(np.int8))
        start=time.perf_counter()
        job=self.runner.execute_async([value],self.buffers)
        status=self.runner.wait(job)
        if status not in (None,0): raise RuntimeError(f'DPU wait failed: {status}')
        elapsed=time.perf_counter()-start
        outputs=[(self.buffers[i].astype(np.float32)*2.0**(-self.outs[i].get_attr('fix_point'))).transpose(0,3,1,2) for i in self.order]
        return outputs,elapsed


class VdmaFullFrame:
    """Read existing 1280x720 BGR video capture ring; no 256x144 pose branch."""
    W,H=1280,720
    BYTES=W*H*3
    def __init__(self,display=False):
        self.fd=os.open('/dev/mem',os.O_RDWR|os.O_SYNC)
        self.regs=mmap.mmap(self.fd,0x10000,flags=mmap.MAP_SHARED,
                           prot=mmap.PROT_READ|mmap.PROT_WRITE,offset=0xA0000000)
        self.capture=mmap.mmap(self.fd,self.BYTES*3,flags=mmap.MAP_SHARED,
                              prot=mmap.PROT_READ,offset=0x70000000)
        self.display=mmap.mmap(self.fd,self.BYTES*3,flags=mmap.MAP_SHARED,
                              prot=mmap.PROT_READ|mmap.PROT_WRITE,offset=0x71000000) if display else None
        self.previous=None

    def read(self):
        deadline=time.monotonic()+2
        while time.monotonic()<deadline:
            status=struct.unpack_from('<I',self.regs,0x34)[0]
            if status & 0x0ff1: raise RuntimeError(f'VDMA capture error/halted, status=0x{status:08x}')
            current=(struct.unpack_from('<I',self.regs,0x28)[0]>>24)&31
            if current>2: raise RuntimeError('VDMA ring index outside three buffers')
            completed=(current+2)%3
            if self.previous is None:
                self.previous=completed
                continue
            if completed==self.previous:
                time.sleep(0.001)
                continue
            frame=np.ndarray((self.H,self.W,3),np.uint8,buffer=self.capture,
                             offset=completed*self.BYTES).copy()
            after=(struct.unpack_from('<I',self.regs,0x28)[0]>>24)&31
            if after!=current: continue
            self.previous=completed
            return True,frame
        raise RuntimeError('No fresh VDMA frame within 2 seconds')

    def present(self,frame):
        if self.display is None: return
        park=struct.unpack_from('<I',self.regs,0x28)[0]
        active=(park>>16)&31
        if active>2: raise RuntimeError('VDMA display index outside three buffers')
        target=(active+1)%3
        view=np.ndarray((self.H,self.W,3),np.uint8,buffer=self.display,offset=target*self.BYTES)
        np.copyto(view,frame)
        del view
        control=struct.unpack_from('<I',self.regs,0)[0]
        struct.pack_into('<I',self.regs,0,control&~2)
        park=struct.unpack_from('<I',self.regs,0x28)[0]
        struct.pack_into('<I',self.regs,0x28,(park&~31)|target)
        deadline=time.monotonic()+0.25
        while ((struct.unpack_from('<I',self.regs,0x28)[0]>>16)&31)!=target:
            if time.monotonic()>deadline: raise RuntimeError('HDMI frame-buffer switch timed out')
            time.sleep(.001)

    def release(self):
        if self.display is not None: self.display.close()
        self.capture.close()
        self.regs.close()
        os.close(self.fd)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--xmodel',type=Path,required=True)
    p.add_argument('--camera',default='vdma')
    p.add_argument('--size',type=int,choices=[384],default=384)
    p.add_argument('--confidence',type=float,default=0.25)
    p.add_argument('--keypoint-confidence',type=float,default=0.25)
    p.add_argument('--hdmi',action='store_true')
    p.add_argument('--preview',action='store_true')
    p.add_argument('--frames',type=int,default=0)
    p.add_argument('--jsonl',type=Path)
    a=p.parse_args()
    check_hardware_fingerprint()
    model=DpuModel(a.xmodel,a.size)
    vdma=a.camera=='vdma'
    camera=VdmaFullFrame(a.hdmi) if vdma else cv2.VideoCapture(int(a.camera) if a.camera.isdigit() else a.camera)
    stream=a.jsonl.open('w') if a.jsonl else None
    count=0
    report=time.monotonic()
    report_count=0
    fps=0.0
    try:
        while not a.frames or count<a.frames:
            start=time.perf_counter()
            ok,frame=camera.read()
            if not ok: break
            x,transform=preprocess(frame,a.size)
            raw,dpu_time=model(x)
            boxes,scores,points=decode(raw,transform,conf=a.confidence)
            pose=points[0] if len(points) else None
            # No extrapolated/synthetic pose on missing evidence.
            if pose is not None:
                good=pose[:,2]>=a.keypoint_confidence
                for i,j in EDGES:
                    if good[i] and good[j]:
                        cv2.line(frame,tuple(pose[i,:2].astype(int)),tuple(pose[j,:2].astype(int)),(0,255,0),2)
                for xy in pose[good,:2]: cv2.circle(frame,tuple(xy.astype(int)),4,(0,255,255),-1)
            cv2.putText(frame,f'YOLO9 DPU {fps:.1f} FPS',(12,28),cv2.FONT_HERSHEY_SIMPLEX,.7,(0,255,0),2)
            before_present=time.perf_counter()
            if vdma: camera.present(frame)
            elapsed=time.perf_counter()-start
            count+=1
            result={'frame':count,'detected':pose is not None,'person_confidence':float(scores[0]) if len(scores) else 0,
                    'keypoints':pose.tolist() if pose is not None else None,
                    'dpu_ms':dpu_time*1000,'capture_inference_decode_draw_ms':(before_present-start)*1000,
                    'loop_including_hdmi_ms':elapsed*1000,'fps':fps}
            if stream: stream.write(json.dumps(result)+'\n')
            if time.monotonic()-report>=1:
                fps=(count-report_count)/(time.monotonic()-report)
                result['fps']=fps
                print(json.dumps(result),flush=True)
                report=time.monotonic()
                report_count=count
                if stream: stream.flush()
            if a.preview:
                cv2.imshow('YOLO9 DPU',frame)
                if cv2.waitKey(1)&255 in (27,ord('q')): break
    finally:
        camera.release()
        if stream: stream.close()
        cv2.destroyAllWindows()


def check_hardware_fingerprint():
    query=subprocess.run(['xdputil','query'],capture_output=True,text=True,timeout=20,check=True)
    # xdputil may prepend informational logging to its JSON document.
    text=query.stdout
    info=json.loads(text[text.index('{'):text.rindex('}')+1])
    values=[]
    def walk(obj):
        if isinstance(obj,dict):
            for key,value in obj.items():
                if 'fingerprint' in key.lower():
                    values.append(int(value,0) if isinstance(value,str) else int(value))
                elif isinstance(value,(dict,list)): walk(value)
        elif isinstance(obj,list):
            for value in obj: walk(value)
    walk(info)
    if not values or any(value!=EXPECTED_FINGERPRINT for value in values):
        raise RuntimeError(f'Board DPU fingerprint mismatch: {values}')
    print(json.dumps({'hardware_fingerprint':hex(EXPECTED_FINGERPRINT),'verified':True}),flush=True)

if __name__=='__main__': main()
