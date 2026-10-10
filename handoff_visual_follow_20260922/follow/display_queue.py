"""Independent HDMI submission, keeping each skeleton with its own source image."""
import queue
import threading
import time

class DisplayQueue:
    def __init__(self,display):
        self.display=display
        self.queue=queue.Queue(maxsize=1)
        self.stop=threading.Event()
        self.error=None
        self.presented=0;self.dropped=0
        self.last_sequence=0
        self.last_presented=None
        self.intervals=[]
        self.frame_age_ms=0.
        self.thread=threading.Thread(target=self.run,name='hdmi-present',daemon=True)
        self.thread.start()

    def check(self):
        if self.error is not None:raise RuntimeError('HDMI worker failed') from self.error

    def submit(self,frame,sequence,captured):
        self.check()
        item=(frame,sequence,captured)
        try:self.queue.put_nowait(item)
        except queue.Full:
            try:self.queue.get_nowait();self.dropped+=1
            except queue.Empty:pass
            self.queue.put_nowait(item)

    def run(self):
        try:
            while not self.stop.is_set():
                try:frame,sequence,captured=self.queue.get(timeout=.1)
                except queue.Empty:continue
                if sequence<=self.last_sequence:raise RuntimeError('Non-increasing rendered frame generation')
                if time.monotonic()-captured>.25:raise RuntimeError('Rendered frame is stale')
                self.display.present(frame)
                now=time.monotonic()
                if self.last_presented is not None:
                    self.intervals.append((now-self.last_presented)*1000)
                    self.intervals=self.intervals[-300:]
                self.last_presented=now
                self.last_sequence=sequence
                self.presented+=1
                self.frame_age_ms=(now-captured)*1000
        except BaseException as exc:self.error=exc

    def close(self):
        self.stop.set();self.thread.join(2)
        if self.thread.is_alive():raise RuntimeError('HDMI worker did not stop; do not change its buffers')
