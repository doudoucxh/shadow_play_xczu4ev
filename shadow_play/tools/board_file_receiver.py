"""Bounded binary UART file receiver. Restores the console on every exit.

Only writes a new /tmp file; never executes a received payload.
"""
import argparse
import hashlib
import os
from pathlib import Path
import re
import signal
import struct
import time

BLOCK = 32768
MAX_FILE = 200 * 1024 * 1024


def resume_info(target, size, allow_resume=False):
    target = Path(target)
    partial = target.with_name(target.name+'.partial')
    if target.exists(): raise FileExistsError('Destination already exists')
    digest = hashlib.sha256()
    offset = 0
    if partial.exists():
        if not allow_resume: raise FileExistsError('Partial already exists')
        offset = partial.stat().st_size
        if offset > size or (offset != size and offset % BLOCK): raise ValueError('Invalid partial length')
        with partial.open('rb') as source:
            for block in iter(lambda: source.read(BLOCK), b''): digest.update(block)
    return offset, digest


def receive(read, write, target, size, expected, allow_resume=False):
    target = Path(target)
    partial = target.with_name(target.name + '.partial')
    if not 0 < size <= MAX_FILE or not re.fullmatch('[a-f0-9]{64}', expected):
        raise ValueError('Invalid file manifest')
    start, digest = resume_info(target, size, allow_resume)

    def exact(n):
        data = bytearray()
        while len(data) < n:
            block = read(n - len(data))
            if not block:
                raise EOFError('Incomplete UART block')
            data.extend(block)
        return bytes(data)

    with partial.open('ab' if allow_resume and partial.exists() else 'xb') as output:
        for index, offset in enumerate(range(start, size, BLOCK), start//BLOCK):
            number, length = struct.unpack('!II', exact(8))
            if number != index or length != min(BLOCK, size-offset):
                raise ValueError('Invalid UART sequence/length')
            checksum, data = exact(32), exact(length)
            if hashlib.sha256(data).digest() != checksum:
                raise ValueError('UART block checksum mismatch')
            output.write(data)
            digest.update(data)
            write(('ACK %d\n' % index).encode())
        if digest.hexdigest() != expected:
            raise ValueError('File checksum mismatch')
        output.flush()
        os.fsync(output.fileno())
    # link is exclusive: never overwrite a concurrent destination.
    os.link(partial, target)
    partial.unlink()
    write(('FILE_OK ' + expected + '\n').encode())


def main():
    import termios
    import tty
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target')
    parser.add_argument('size', type=int)
    parser.add_argument('sha256')
    parser.add_argument('--baud', type=int, choices=[460800, 921600], default=921600)
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    if not re.fullmatch(r'/tmp/[A-Za-z0-9_-][A-Za-z0-9_.-]*', args.target):
        parser.error('Only a new simple /tmp filename is accepted')
    old = termios.tcgetattr(0)
    console = Path('/proc/sys/kernel/printk')
    verbosity = console.read_text()

    def timeout(*unused):
        raise TimeoutError('UART receive timed out')

    signal.signal(signal.SIGALRM, timeout)
    try:
        offset, prefix = resume_info(args.target, args.size, args.resume)
        print('BINARY_READY %d %s' % (offset, prefix.hexdigest()), flush=True)
        signal.alarm(15)
        console.write_text('1 '+ ' '.join(verbosity.split()[1:]))
        time.sleep(.4)
        tty.setraw(0)
        fast = termios.tcgetattr(0)
        fast[4] = fast[5] = getattr(termios, 'B%d' % args.baud)
        termios.tcsetattr(0, termios.TCSADRAIN, fast)

        def read(n):
            signal.alarm(15)
            return os.read(0, n)

        receive(read, lambda data: os.write(1, data), args.target, args.size, args.sha256, args.resume)
        time.sleep(.4)
    finally:
        signal.alarm(0)
        termios.tcsetattr(0, termios.TCSADRAIN, old)
        console.write_text(verbosity)
        print('CONSOLE_RESTORED', flush=True)


if __name__ == '__main__':
    main()
