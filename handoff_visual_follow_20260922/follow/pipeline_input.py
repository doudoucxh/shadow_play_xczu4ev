"""Exact uint8-to-INT8 preparation and bounded latest-frame camera producer."""
import queue
import concurrent.futures
import struct
import threading
import time
import cv2
import numpy as np
from orientation import orient_frame

class BlockCopier:
    def __init__(self):
        self.pool=concurrent.futures.ThreadPoolExecutor(max_workers=2,thread_name_prefix='capture-half')

    def copy(self,source):
        destination=np.empty(source.shape,np.uint8)
        src=source.reshape(-1);dst=destination.reshape(-1);half=src.size//2
        futures=[self.pool.submit(np.copyto,dst[:half],src[:half]),
                 self.pool.submit(np.copyto,dst[half:],src[half:])]
        for future in futures:future.result()
        return destination

    def close(self):self.pool.shutdown(wait=True)

class QuantizedInput:
    def __init__(self,fix):
        self.canvas=np.full((384,384,3),114,np.uint8)
        self.lut=np.clip(np.rint((np.arange(256,dtype=np.float32)/255)*(2.**fix)),-128,127).astype(np.int8)

    def __call__(self,frame):
        if frame.shape!=(720,1280,3) or frame.dtype!=np.uint8:
            raise ValueError('Expected upright CPU-owned BGR 1280x720 input')
        self.canvas[84:300]=cv2.resize(frame,(384,216),interpolation=cv2.INTER_LINEAR)
        rgb=cv2.cvtColor(self.canvas,cv2.COLOR_BGR2RGB)
        value=cv2.LUT(rgb,self.lut.view(np.uint8)).view(np.int8)[None]
        return value,(.3,0,84,1280,720)

def safe_snapshot(before,after,seconds):
    # Verified camera frame interval >34 ms. During a <30 ms read the writer
    # may move once, but cannot reach source=(before-1)%3 until its SECOND move.
    # Starting the timer BEFORE the initial writer read bounds the whole snapshot.
    return 0<=before<3 and after in (before,(before+1)%3) and 0<=seconds<.030

class LatestCamera:
    """One-slot queue: never accumulate latency or render a stale inference on a new image."""
    def __init__(self,camera):
        self.camera=camera
        self.stop=threading.Event()
        self.queue=queue.Queue(maxsize=1)
        self.error=None
        self.published=0;self.dropped=0;self.rejected=0
        self.copier=BlockCopier()
        self.thread=threading.Thread(target=self.produce,name='camera-copy',daemon=True)
        self.thread.start()

    def writer(self):
        state=struct.unpack_from('<I',self.camera.regs,0x34)[0]
        if state&0x8ff1:raise RuntimeError(f'Camera DMA error {state:x}')
        value=(struct.unpack_from('<I',self.camera.regs,0x28)[0]>>24)&31
        if value>2:raise RuntimeError('Camera index outside triple buffer')
        return value

    def produce(self):
        try:
            previous=self.writer()
            deadline=time.monotonic()+2
            while not self.stop.is_set():
                start=time.monotonic()
                current=self.writer()
                if current==previous:
                    if time.monotonic()>deadline:raise RuntimeError('No coherent fresh camera frame for 2 seconds')
                    self.stop.wait(.0005)
                    continue
                previous=current
                source=(current+2)%3
                view=np.ndarray((720,1280,3),np.uint8,buffer=self.camera.capture,offset=source*self.camera.BYTES)
                raw=self.copier.copy(view)
                del view
                after=self.writer()
                captured=time.monotonic()
                if not safe_snapshot(current,after,captured-start):
                    self.rejected+=1
                    if captured>deadline:raise RuntimeError('Camera copies repeatedly cross frame boundary')
                    continue
                deadline=captured+2
                frame=orient_frame(raw,180)
                self.published+=1
                item=(frame,self.published,captured)
                try:self.queue.put_nowait(item)
                except queue.Full:
                    try:self.queue.get_nowait();self.dropped+=1
                    except queue.Empty:pass
                    self.queue.put_nowait(item)
        except BaseException as exc:self.error=exc
        finally:self.copier.close()

    def read(self):
        if self.error is not None:raise RuntimeError('Camera producer failed') from self.error
        try:item=self.queue.get(timeout=2.5)
        except queue.Empty:raise RuntimeError('Camera producer timed out') from self.error
        if self.error is not None:raise RuntimeError('Camera producer failed') from self.error
        if time.monotonic()-item[2]>.25:raise RuntimeError('Refusing stale captured frame')
        return item

    def close(self):
        self.stop.set();self.thread.join(3)
        if self.thread.is_alive():raise RuntimeError('Camera producer did not stop; do not unmap its buffers')
