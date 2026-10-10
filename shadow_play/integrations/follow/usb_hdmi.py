"""Independent HDMI output for the reviewed servo10+vision PL image.

Does not initialize OV5640, inspect S2MM capture, or access servo registers.
Run with --display none when the reviewed runtime image is not loaded.
"""
import json
import mmap
import os
from pathlib import Path
import sys
import time

import numpy as np

sys.path.append(str(Path(__file__).resolve().parents[1] / 'calibration'))
from mmio32 import WordAccess

IMAGE_SHA = '824779d32865ad5d3f70664fa185b353d23cd5d56502cf88bfbd8aa1e7e2ee3f'
VTC_TIMING = {0x60: 1280 | (720 << 16), 0x68: 0, 0x6c: 0x7f,
              0x70: 1650, 0x74: 750 | (750 << 16), 0x78: 1390 | (1430 << 16),
              0x7c: 1280 | (1280 << 16), 0x80: 724 | (729 << 16),
              0x84: 1390 | (1390 << 16), 0x88: 1280 | (1280 << 16),
              0x8c: 724 | (729 << 16), 0x90: 1390 | (1390 << 16), 0x94: 720 << 16}


class UsbHdmiDisplay:
    N = 1280 * 720 * 3
    BASE = 0x71000000
    OFFSETS = (0, 0x50, 0x54, 0x58, 0x5c, 0x60, 0x64)

    def __init__(self):
        marker = Path('/run/shadow-pwm-loaded.json')
        if not marker.exists() or json.loads(marker.read_text()).get('sha256') != IMAGE_SHA:
            raise RuntimeError('USB HDMI requires the reviewed G13 servo10_vision image; '
                               'use --display none for USB/DPU tests without it')
        self.fd = None
        self.regs = self.vtc = self.out = self.words = self.vtc_words = None
        self.changed = False
        try:
            self.fd = os.open('/dev/mem', os.O_RDWR | os.O_SYNC)
            self.regs = mmap.mmap(self.fd, 0x10000, offset=0xA0000000)
            self.vtc = mmap.mmap(self.fd, 0x10000, offset=0xA0020000)
            self.words, self.vtc_words = WordAccess(self.regs), WordAccess(self.vtc)
            self.out = mmap.mmap(self.fd, self.N * 3, offset=self.BASE)
            self.saved = {o: self.rd(o) for o in self.OFFSETS}
            self.saved_park = self.rd(0x28) & 31
            self.saved_vtc = {o: self.vtc_words.read(o) for o in (0, *VTC_TIMING)}
        except BaseException:
            self.close()
            raise

    def rd(self, offset):
        return self.words.read(offset)

    def wr(self, offset, value):
        self.words.write(offset, value)

    def reset(self):
        self.wr(0, 4)
        deadline = time.monotonic() + 1
        while self.rd(0) & 4:
            if time.monotonic() > deadline:
                raise RuntimeError('HDMI DMA reset timeout')
            time.sleep(.001)

    def copy(self, frame, index):
        if frame.shape != (720, 1280, 3) or frame.dtype != np.uint8:
            raise ValueError('HDMI requires a 720p BGR frame')
        view = np.ndarray(frame.shape, np.uint8, buffer=self.out, offset=index*self.N)
        np.copyto(view, frame)
        del view

    def start(self, frame):
        self.changed = True
        self.reset()
        for index in range(3):
            self.copy(frame, index)
        self.vtc_words.write(0, 0x80000000)
        time.sleep(.001)
        self.vtc_words.write(0, 0)
        for offset, value in VTC_TIMING.items():
            self.vtc_words.write(offset, value)
        self.vtc_words.write(0, 0x03fdef06)
        self.wr(4, 0xffffffff)
        self.wr(0x54, 3840)
        self.wr(0x58, 3840)
        for index in range(3):
            self.wr(0x5c + index*4, self.BASE + index*self.N)
        self.wr(0x28, self.rd(0x28) & ~31)
        self.wr(0, 1)  # Parked MM2S, no capture Genlock.
        self.wr(0x50, 720)
        time.sleep(.05)
        self.present(frame)

    def check(self):
        # USB has no relationship to old camera/pose S2MM errors.
        state = self.rd(4)
        if state & 0x8ff1:
            raise RuntimeError('USB HDMI MM2S error: {:x}'.format(state))

    def present(self, frame):
        self.check()
        active = (self.rd(0x28) >> 16) & 31
        if active > 2:
            raise RuntimeError('Invalid HDMI frame index')
        target = (active + 1) % 3
        self.copy(frame, target)
        self.wr(0x28, (self.rd(0x28) & ~31) | target)
        deadline = time.monotonic() + .3
        while (self.rd(0x28) >> 16) & 31 != target:
            if time.monotonic() > deadline:
                raise RuntimeError('HDMI frame switch timeout')
            time.sleep(.001)
        self.check()

    def restore(self):
        if not self.changed:
            return
        self.reset()
        self.wr(4, 0xffffffff)
        for offset in self.OFFSETS[1:]:
            if offset != 0x50:
                self.wr(offset, self.saved[offset])
        self.wr(0x28, (self.rd(0x28) & ~31) | self.saved_park)
        for offset in VTC_TIMING:
            self.vtc_words.write(offset, self.saved_vtc[offset])
        self.vtc_words.write(0, self.saved_vtc[0] & ~0x80000000)
        self.wr(0, self.saved[0] & ~4)
        if self.saved[0] & 1:
            self.wr(0x50, self.saved[0x50])
        self.changed = False

    def close(self):
        for access in (self.words, self.vtc_words):
            if access is not None:
                access.close()
        for buffer in (self.regs, self.vtc, self.out):
            if buffer is not None:
                buffer.close()
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
