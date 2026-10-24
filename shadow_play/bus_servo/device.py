"""Board-side bus driver and deterministic offline device."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import mmap
import os
from pathlib import Path
import threading
import time

from . import protocol

BASE = 0xA0060000
IDENTITY = 0x42533130


class Mmio:
    def __init__(self, release_manifest, marker='/run/shadow-bus-servo-loaded.json'):
        # Check the boot-bound loaded-image evidence BEFORE touching an address
        # that does not exist in the old PWM image.
        import fcntl
        from ..integrations.calibration.mmio32 import WordAccess
        manifest = json.loads(Path(release_manifest).read_text())
        current = json.loads(Path(marker).read_text())
        boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        if (current.get('boot_id') != boot or current.get('sha256') != manifest.get('sha256')
                or manifest.get('identity') != 'BS10' or manifest.get('register_base') != BASE
                or current.get('identity') != 'BS10' or manifest.get('checks') != 'passed'):
            raise RuntimeError('Current boot has no verified BS10 candidate; do not use old UART/PWM addresses')
        self.lock = open('/run/shadow-pwm.lock', 'a')
        self.words = self.memory = self.fd = None
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.fd = os.open('/dev/mem', os.O_RDWR | os.O_SYNC)
            self.memory = mmap.mmap(self.fd, 4096, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=BASE)
            self.words = WordAccess(self.memory)
            if (self.read(0) != IDENTITY or self.read(4) != 1 or self.read(0x18) != 100000000
                    or self.read(0x1c) != 115200):
                raise RuntimeError('BS10 identity/clock/baud mismatch')
            if self.read(8) or self.read(0x10):
                raise RuntimeError('Bus has a latched fault or an existing lease; inspect before connecting')
        except BaseException:
            self.close()
            raise

    def read(self, offset):
        return self.words.read(offset)

    def write(self, offset, value):
        self.words.write(offset, value)

    def close(self):
        if self.words is not None:
            self.words.close(); self.words = None
        if self.memory is not None:
            self.memory.close(); self.memory = None
        if self.fd is not None:
            os.close(self.fd); self.fd = None
        self.lock.close()


class WireBus:
    def __init__(self, registers, offset, write_lock):
        self.reg, self.offset, self.write_lock = registers, offset, write_lock

    def status(self):
        value = self.reg.read(self.offset)
        if value >> 24 or self.reg.read(8):
            raise protocol.ProtocolError('UART framing/overflow/watchdog fault; no retry')
        return bool(value & 1), (value >> 8) & 511

    def exchange(self, request, expects_reply=True, reply_length=None):
        busy, count = self.status()
        if busy or count:
            raise protocol.ProtocolError('Bus is not idle / has stale bytes; no discard or resend')
        if not isinstance(request, bytes) or not 1 <= len(request) <= 256:
            raise ValueError('Invalid UART transaction')
        with self.write_lock:
            for i, byte in enumerate(request):
                self.reg.write(self.offset + 8, i << 8 | byte)
            self.reg.write(self.offset + 12, len(request))
        deadline = time.monotonic() + .12
        reply = bytearray()
        last_byte = None
        while time.monotonic() < deadline:
            busy, count = self.status()
            if count:
                for _ in range(count):
                    reply.append(self.reg.read(self.offset + 4) & 255)
                last_byte = time.monotonic()
                if len(reply) > 1024:
                    raise protocol.ProtocolError('Oversized response')
            if not busy:
                if not expects_reply:
                    # Position commands normally have no ACK. Preserve any
                    # unexpected response as an error instead of assuming success.
                    if reply:
                        raise protocol.ProtocolError(f'Unexpected motion response: {bytes(reply)!r}')
                    return b''
                complete = len(reply) >= reply_length if reply_length is not None else b'!' in reply
                if complete and last_byte is not None and time.monotonic() - last_byte >= .0005:
                    return bytes(reply)
            time.sleep(.0001)
        raise TimeoutError('Servo reply timeout; command is not retried')


class BusDevice:
    simulation = False

    def __init__(self, profile, registers):
        self.profile, self.reg = profile, registers
        self.pool = ThreadPoolExecutor(max_workers=2)
        write_lock = threading.Lock()
        self.buses = {name: WireBus(registers, offset, write_lock)
                      for name, offset in [('person', 0x100), ('tiger', 0x200)]}
        self.claimed = False
        self.failed = False
        self.versions = {}

    def _parallel(self, axes, action):
        groups = [[a for a in axes if a.bus == b] for b in ('person', 'tiger')]
        def run(group):
            return [(a.number, action(a, self.buses[a.bus])) for a in group]
        futures = [self.pool.submit(run, group) for group in groups if group]
        results, errors = {}, []
        for future in futures:
            try:
                results.update(future.result())
            except Exception as exc:
                errors.append(exc)
        if errors:
            self.failed = True
            if self.claimed:
                self.stop()
            raise errors[0]
        return results

    def connect(self):
        def identify(a, bus):
            version = protocol.parse_reply(bus.exchange(protocol.command(a.ident, 'VER')), a.ident, 'version')
            mode = protocol.parse_reply(bus.exchange(protocol.command(a.ident, 'MOD')), a.ident, 'mode')
            expected_modes = (3, 4) if a.span == 180 else (1, 2)
            if mode not in expected_modes:
                raise ValueError(f'Axis {a.number}: servo mode does not match angle profile')
            return {'version': version, 'mode': mode}
        self.versions = self._parallel(list(self.profile.axes.values()), identify)
        return self.read(list(range(1, 11)))

    def kick(self):
        if self.failed or self.reg.read(8):
            raise RuntimeError('Bus fault latched; no automatic resume')
        if self.claimed:
            if not self.reg.read(0x10):
                self.failed = True
                raise RuntimeError('Motion lease lost; no automatic re-arm')
            self.reg.write(0x14, 0x4b49434b)

    def read(self, numbers):
        self.kick()
        def acquire(a, bus):
            protocol.parse_health(bus.exchange(protocol.health_request(a.ident), reply_length=7), a.ident)
            p = protocol.parse_reply(bus.exchange(protocol.command(a.ident, 'RAD')), a.ident, 'position')
            return {'p': p, 'at': time.monotonic()}
        return self._parallel(self.profile.select(numbers), acquire)

    def _lease(self):
        if self.failed:
            raise RuntimeError('Reconnect after inspecting failure; no automatic retry')
        if not self.claimed:
            self.reg.write(0x10, 0x41524d31)
            if not self.reg.read(0x10):
                raise RuntimeError('Unable to establish FPGA motion lease')
            self.claimed = True
        self.kick()

    def release(self, numbers):
        axes = self.profile.select(numbers)
        self._lease()
        def release_axis(a, bus):
            return protocol.parse_reply(bus.exchange(protocol.command(a.ident, 'ULK')), a.ident, 'ok')
        self._parallel(axes, release_axis)

    def move(self, targets, milliseconds):
        axes = self.profile.select([int(n) for n in targets])
        frames = {a.number: protocol.move(a.ident, a.check_position(targets[str(a.number)]), milliseconds) for a in axes}
        self._lease()
        self._parallel(axes, lambda a, bus: bus.exchange(frames[a.number], False))
        # Transmission completion is not physical-position verification.

    def stop(self):
        self.reg.write(0x0c, 0x53544f50)
        self.claimed = False
        # Broadcast release can generate addressed, staggered replies. Preserve
        # and drain THIS stop's bytes so reconnect cannot mistake them for fresh
        # feedback. Do not reset FIFOs or retry the broadcast.
        started = time.monotonic()
        budget = min(.8, max(.08, (max(a.ident for a in self.profile.axes.values()) + 1) * .0028 + .05))
        raw = {'person': bytearray(), 'tiger': bytearray()}
        while time.monotonic() - started < budget:
            for name, bus in self.buses.items():
                state = self.reg.read(bus.offset)
                count = (state >> 8) & 511
                for _ in range(min(count, 255)):
                    raw[name].append(self.reg.read(bus.offset + 4) & 255)
            time.sleep(.001)
        self.last_stop = {'state': 'release_requested', 'physical_stop_verified': False,
                          'reply_hex': {name: bytes(data).hex() for name, data in raw.items()}}
        return self.last_stop

    def close(self):
        try:
            if self.claimed:
                self.stop()
            self.pool.shutdown(wait=True)
        finally:
            self.reg.close()


class SimulationDevice:
    simulation = True

    def __init__(self, profile):
        self.profile = profile
        self.positions = {n: 1500 for n in profile.axes}
        self.motions = {}
        self.released = set()

    def connect(self):
        return self.read(list(self.positions))

    def kick(self):
        pass

    def read(self, numbers):
        now = time.monotonic()
        for n, (start, end, t, seconds) in list(self.motions.items()):
            f = min(1, (now - t) / seconds)
            self.positions[n] = round(start + (end - start) * f)
            if f >= 1:
                del self.motions[n]
        return {a.number: {'p': self.positions[a.number], 'at': now} for a in self.profile.select(numbers)}

    def release(self, numbers):
        self.read(numbers)
        for n in numbers:
            self.motions.pop(n, None)
            self.released.add(n)

    def move(self, targets, milliseconds):
        self.read([int(n) for n in targets])
        now = time.monotonic()
        for n, p in targets.items():
            n = int(n)
            self.profile.axes[n].check_position(p)
            self.released.discard(n)
            self.motions[n] = self.positions[n], p, now, milliseconds / 1000

    def drag(self, targets):
        for n, p in targets.items():
            n = int(n)
            if n not in self.released:
                raise ValueError('Release axis before simulated teaching')
            self.positions[n] = self.profile.axes[n].check_position(p)

    def stop(self):
        self.release(list(self.positions))
        return 'simulation_released'

    def close(self):
        self.stop()
