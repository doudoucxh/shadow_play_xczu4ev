"""Explicit native 32-bit device access; never use struct.pack_into for MMIO."""
import ctypes
from pathlib import Path
import sys


class WordAccess:
    def __init__(self, buffer, library=None):
        if sys.byteorder != 'little':
            raise RuntimeError('Little-endian host required')
        self.size = len(buffer)
        if self.size < 4 or self.size % 4:
            raise ValueError('Register buffer must contain complete 32-bit words')
        library = library or Path(__file__).with_name('libservo_mmio32.so')
        self.native = ctypes.CDLL(str(Path(library).resolve()))
        self.native.servo_mmio_abi.argtypes = []
        self.native.servo_mmio_abi.restype = ctypes.c_uint32
        if self.native.servo_mmio_abi() != 1:
            raise RuntimeError('Wrong MMIO library ABI')
        self.native.servo_mmio_read32.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        self.native.servo_mmio_read32.restype = ctypes.c_uint32
        self.native.servo_mmio_write32.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32]
        self.native.servo_mmio_write32.restype = None
        self.view = (ctypes.c_ubyte * self.size).from_buffer(buffer)
        self.address = ctypes.addressof(self.view)
        if self.address % 4:
            self.close()
            raise ValueError('Unaligned register buffer')

    def check_offset(self, offset):
        if self.view is None:
            raise RuntimeError('MMIO access is closed')
        if type(offset) is not int or offset < 0 or offset % 4 or offset + 4 > self.size:
            raise ValueError('Aligned in-range register offset required')

    def read(self, offset):
        self.check_offset(offset)
        return self.native.servo_mmio_read32(self.address, offset)

    def write(self, offset, value):
        self.check_offset(offset)
        if type(value) is not int or not 0 <= value <= 0xffffffff:
            raise ValueError('Unsigned 32-bit register value required')
        self.native.servo_mmio_write32(self.address, offset, value)

    def close(self):
        self.view = None
        self.address = None
