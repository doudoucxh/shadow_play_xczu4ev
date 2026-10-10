"""FOLLOW entry with the shadow_play camera v2 sender integrated.

Source: handoff_visual_follow_20260922/follow/board_follow.py.
This review copy preserves the vision/display logic; additions connect PoseSender.
Original handoff file and archives are unchanged. Requires the original board runtime.

Reversible on-board YOLO test with independent CPU-owned HDMI buffers.

No SD writes. Inference and display use the SAME upright CPU-owned frame.
SIGTERM/normal exit restores the original shared-ring display configuration.
"""
import argparse
import ctypes
import fcntl
import json
import mmap
import os
import signal
import struct
import sys
import time
import cv2
import numpy as np
sys.path.insert(0, '/opt/shadow/yolo_pose9/runtime')
from runtime import DpuModel, VdmaFullFrame, check_hardware_fingerprint, EDGES
from postprocess import preprocess, decode
from orientation import orient_frame
from fast_decode import decode_int8
from pipeline_input import QuantizedInput, LatestCamera
from display_queue import DisplayQueue
from pose_responsive import PoseStabilizer
from pose_sender import PoseSender

class Display:
    N = 1280 * 720 * 3
    BASE = 0x71000000
    OFFSETS = (0,0x50,0x54,0x58,0x5c,0x60,0x64)

    def __init__(self, regs):
        self.regs = regs
        self.fd = os.open('/dev/mem',os.O_RDWR|os.O_SYNC)
        self.out = mmap.mmap(self.fd,self.N*3,offset=self.BASE)
        self.saved = {o:self.rd(o) for o in self.OFFSETS}
        self.saved_park = self.rd(0x28)&31
        self.changed = False
        if [self.saved[o] for o in (0x5c,0x60,0x64)] != [0x70000000+i*self.N for i in range(3)]:
            self.close()
            raise RuntimeError('Expected original shared-ring display before takeover')
        if self.saved[0] & 0x8b != 0x8b:
            self.close()
            raise RuntimeError('Expected running circular Genlock display')

    def rd(self,o): return struct.unpack_from('<I',self.regs,o)[0]
    def wr(self,o,x):
        ctypes.c_uint32.from_buffer(self.regs,o).value=x
        return self.rd(o)

    def reset(self):
        self.wr(0,4)
        deadline=time.monotonic()+1
        while self.rd(0)&4:
            if time.monotonic()>deadline: raise RuntimeError('HDMI DMA reset timed out')
            time.sleep(.001)

    def copy(self,frame,index):
        if frame.shape != (720,1280,3) or frame.dtype != np.uint8:
            raise ValueError('Expected CPU-owned 720p uint8 BGR image')
        target=np.ndarray(frame.shape,np.uint8,buffer=self.out,offset=index*self.N)
        np.copyto(target,frame)
        del target

    def start(self,frame):
        self.copy(frame,0)
        self.changed=True
        self.reset()
        self.wr(4,0xffffffff)
        self.wr(0x54,3840); self.wr(0x58,3840)
        for i in range(3): self.wr(0x5c+4*i,self.BASE+i*self.N)
        self.wr(0x28,self.rd(0x28)&~31)
        # Parked mode, Genlock explicitly disabled for the independent display ring.
        self.wr(0,1)
        time.sleep(.001)
        self.wr(0x50,720)
        time.sleep(.05)
        self.check()
        self.present(frame)  # Prove an actual frame-boundary switch before declaring ready.

    def check(self):
        for off in (4,0x34):
            if self.rd(off)&0x8ff1: raise RuntimeError(f'Video DMA error {off:x}: {self.rd(off):x}')

    def present(self,frame):
        self.check()
        active=(self.rd(0x28)>>16)&31
        if active>2: raise RuntimeError('Invalid HDMI frame index')
        target=(active+1)%3
        self.copy(frame,target)
        self.wr(0x28,(self.rd(0x28)&~31)|target)
        deadline=time.monotonic()+.3
        while (self.rd(0x28)>>16)&31 != target:
            if time.monotonic()>deadline:raise RuntimeError('HDMI park switch timeout')
            time.sleep(.001)
        self.check()

    def restore(self):
        if not self.changed:return
        self.reset()
        self.wr(4,0xffffffff)
        for o in (0x54,0x58,0x5c,0x60,0x64):self.wr(o,self.saved[o])
        self.wr(0x28,(self.rd(0x28)&~31)|self.saved_park)
        self.wr(0,self.saved[0]&~4)
        time.sleep(.001)
        self.wr(0x50,self.saved[0x50])
        time.sleep(.1)
        self.check()
        self.changed=False
        print('ORIGINAL_VIDEO_REGISTERS_RESTORED',flush=True)

    def close(self):
        self.out.close()
        os.close(self.fd)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--frames',type=int,default=0)
    parser.add_argument('--pose-port',type=int,default=56000,help='shadow_play loopback UDP input port')
    args=parser.parse_args()
    if not 1 <= args.pose_port <= 65535:parser.error('--pose-port must be in [1, 65535]')
    lock=open('/tmp/shadow-yolo-board-test.lock','w')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    stopping=False
    def stop(*_):
        nonlocal stopping
        stopping=True
    signal.signal(signal.SIGTERM,stop)
    signal.signal(signal.SIGINT,stop)
    cv2.setNumThreads(1)
    check_hardware_fingerprint()
    model=DpuModel('/opt/shadow/yolo_pose9/model/yolo_pose9_b4096.xmodel')
    fixes=[model.outs[j].get_attr('fix_point') for j in model.order]
    camera=VdmaFullFrame(False)
    pose_fd=os.open('/dev/mem',os.O_RDONLY|os.O_SYNC)
    pose_regs=mmap.mmap(pose_fd,65536,prot=mmap.PROT_READ,offset=0xA0010000)
    display=None
    renderer=None
    producer=LatestCamera(camera)
    prepare=QuantizedInput(model.input_fix)
    reference_verified=False
    stabilizer=PoseStabilizer()
    count=0; report=time.monotonic(); last_count=0; last_presented=0; fps=0.
    sender=None
    try:
        # Construction inside try keeps the original cleanup active on failure.
        sender=PoseSender(port=args.pose_port)
        while not stopping and (not args.frames or count<args.frames):
            start=time.monotonic()
            if renderer is not None:renderer.check()
            if struct.unpack_from('<I',pose_regs,0x34)[0]&0x8ff1:raise RuntimeError('Pose drain DMA error')
            frame,sequence,captured=producer.read()
            value,transform=prepare(frame)
            t=time.monotonic()
            job=model.runner.execute_async([value],model.buffers)
            status=model.runner.wait(job)
            if status not in (None,0):raise RuntimeError(f'DPU wait failed: {status}')
            dpu_ms=(time.monotonic()-t)*1000
            boxes,scores,points=decode_int8([model.buffers[j] for j in model.order],fixes,transform)
            if len(points) and not reference_verified:
                original,original_transform=preprocess(frame,384)
                expected=np.ascontiguousarray(np.clip(np.rint(original.transpose(0,2,3,1)*(2.**model.input_fix)),-128,127).astype(np.int8))
                np.testing.assert_array_equal(value,expected)
                raw=[(model.buffers[j].astype(np.float32)*2.**(-model.outs[j].get_attr('fix_point'))).transpose(0,3,1,2) for j in model.order]
                for actual,reference in zip((boxes,scores,points),decode(raw,original_transform)):
                    np.testing.assert_allclose(actual,reference,rtol=1e-6,atol=1e-4)
                reference_verified=True
                print('POSITIVE_FRAME_INPUT_AND_DECODE_PARITY_OK',flush=True)
            t_stable=time.monotonic()
            pose=stabilizer.update(boxes,scores,points,captured)
            stability_ms=(time.monotonic()-t_stable)*1000
            # Final tracked pose, including None; do not reuse old coordinates.
            sender.publish(pose,sequence,captured,stabilizer.track_id)
            if pose is not None:
                for a,b in EDGES:
                    if min(pose[a,2],pose[b,2])>=.25:
                        cv2.line(frame,tuple(np.rint(pose[a,:2]).astype(int)),tuple(np.rint(pose[b,:2]).astype(int)),(0,255,0),3)
                for j,(px,py,c) in enumerate(pose):
                    if c>=.25:
                        pos=(round(float(px)),round(float(py)))
                        cv2.circle(frame,pos,5,(0,255,255),-1)
            cv2.putText(frame,f'YOLOv8n Pose9 | FOLLOW | ROT180 | {fps:.1f} FPS',(14,30),cv2.FONT_HERSHEY_SIMPLEX,.72,(0,255,0),2)
            if pose is None:cv2.putText(frame,'NO TRACK',(14,60),cv2.FONT_HERSHEY_SIMPLEX,.7,(0,200,255),2)
            if display is None:
                display=Display(camera.regs)
                display.start(frame)
                renderer=DisplayQueue(display)
                print('YOLO_HDMI_READY input_rotation=180 display=upright buffers=0x71000000',flush=True)
            else:
                renderer.submit(frame,sequence,captured)
            count+=1
            now=time.monotonic()
            if now-report>=2 or count==1:
                inference_fps=(count-last_count)/(now-report)
                fps=(renderer.presented-last_presented)/(now-report)
                last_presented=renderer.presented
                print('YOLO_STATUS '+json.dumps(dict(frames=count,displayed=renderer.presented,fps=fps,inference_fps=inference_fps,dpu_ms=dpu_ms,
                    display_drops=renderer.dropped,display_frame_age_ms=renderer.frame_age_ms,
                    display_interval_p95_ms=float(np.percentile(renderer.intervals,95)) if renderer.intervals else None,
                    display_interval_max_ms=max(renderer.intervals) if renderer.intervals else None,
                    loop_ms=(now-start)*1000,frame_age_ms=(now-captured)*1000,
                    track_id=stabilizer.track_id,selected_person=stabilizer.selected,stability_ms=stability_ms,
                    sequence=sequence,producer_frames=producer.published,dropped=producer.dropped,rejected=producer.rejected,people=len(scores),confidence=float(scores[stabilizer.selected]) if stabilizer.selected is not None else 0,
                    video_status=[hex(display.rd(o)) for o in (4,0x34)],
                    pose_status=hex(struct.unpack_from('<I',pose_regs,0x34)[0]))),flush=True)
                report=now;last_count=count
    finally:
        try:
            if sender is not None:sender.close()
        finally:
            try:
                if renderer is not None:renderer.close()
                if display is not None:display.restore()
            finally:
                if display is not None:display.close()
                producer.close()
                pose_regs.close();os.close(pose_fd);camera.release();lock.close()

if __name__=='__main__':main()
