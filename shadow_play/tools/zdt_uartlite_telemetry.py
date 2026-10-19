"""Single, non-retrying telemetry request on one reviewed PL UART Lite port.

No device enable, move, homing, position reset or UART FIFO-reset writes.
Run only after explicitly installing and verifying the dual-UART image.
"""
import argparse
import json
import mmap
import os
from pathlib import Path
import time

from zdt_readonly_protocol import decode, query

PORTS = {
    'person': {'base': 0xA0040000, 'tx_pin': 'F15', 'rx_pin': 'H13'},
    'tiger': {'base': 0xA0050000, 'tx_pin': 'H14', 'rx_pin': 'L13'},
}


class TelemetryError(RuntimeError):
    pass


class QueryPort:
    """Word-register transport; callers cannot supply arbitrary transmit data."""

    def __init__(self, registers, *, clock=time.monotonic, sleep=time.sleep):
        self.reg = registers
        self.clock = clock
        self.sleep = sleep
        self.used = False
        self.received = bytearray()
        self.tx_bytes_queued = 0
        self.phase = 'unused'
        self.status_changes = []

    def diagnostics(self):
        return dict(phase=self.phase, tx_bytes_queued=self.tx_bytes_queued,
                    uart_status_changes=self.status_changes,
                    wire_tx_verified=False)

    def status(self):
        value = self.reg.read(8)
        if not self.status_changes or value != self.status_changes[-1]:
            # Bound diagnostics even if a faulty input oscillates continuously.
            if len(self.status_changes) < 32:
                self.status_changes.append(value)
        if value & 0xE0:
            raise TelemetryError('UART parity/framing/overrun error: 0x%02x' % value)
        if value & 0x10:
            raise TelemetryError('UART is owned by an interrupt-enabled client')
        return value

    def request(self, address, kind, *, checksum_mode, firmware_kind):
        packet = query(address, kind, checksum_mode=checksum_mode)
        if kind == 'position' and firmware_kind not in ('Emm', 'X'):
            raise TelemetryError('Position requires an explicit firmware type')
        if self.used:
            raise TelemetryError('One request per port instance; no automatic retry')
        self.used = True
        self.phase = 'checking_idle'
        # A nonempty FIFO is evidence of another transaction, not data to drop.
        quiet_until = self.clock() + 0.020
        while True:
            status = self.status()
            if status & 3 or not status & 4 or status & 8:
                raise TelemetryError('UART is not idle; no bytes were sent')
            if self.clock() >= quiet_until:
                break
            self.sleep(0.0002)
        started = self.clock()
        # At idle a 16-byte TX FIFO has room for this complete 3-byte query.
        self.phase = 'queueing_query'
        for value in packet:
            self.reg.write(4, value)
            self.tx_bytes_queued += 1
        self.phase = 'awaiting_reply'
        deadline = started + 0.350
        last_byte_at = None
        while self.clock() < deadline:
            status = self.status()
            if status & 1:
                self.received.append(self.reg.read(0) & 255)
                last_byte_at = self.clock()
                if len(self.received) > 16:
                    raise TelemetryError('Oversize or unsolicited reply')
            elif last_byte_at is not None and self.clock() - last_byte_at >= 0.020:
                if not status & 4:
                    raise TelemetryError('TX did not return idle')
                result = decode(address, kind, bytes(self.received),
                                checksum_mode=checksum_mode, firmware_kind=firmware_kind)
                result.update(freshness_verified=True,
                              freshness_basis='RX empty for 20ms, bytes received after this sole query',
                              query_hex=packet.hex(), reply_hex=self.received.hex(),
                              elapsed_seconds=self.clock() - started)
                self.phase = 'complete'
                return result
            else:
                self.sleep(0.0002)
        raise TelemetryError('Reply timeout; no automatic resend')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rail', required=True, choices=PORTS)
    parser.add_argument('--address', required=True, type=int)
    parser.add_argument('--query', required=True, choices=('version', 'status', 'position'))
    parser.add_argument('--checksum-mode', required=True, choices=('fixed_6b',))
    parser.add_argument('--firmware-kind', required=True, choices=('Emm', 'X'))
    parser.add_argument('--boot-id', required=True)
    parser.add_argument('--image-sha', required=True)
    parser.add_argument('--expected-sequence', required=True, type=int)
    parser.add_argument('--execute-query', action='store_true')
    args = parser.parse_args()
    packet = query(args.address, args.query, checksum_mode=args.checksum_mode)
    if not args.execute_query:
        print(json.dumps(dict(mode='OFFLINE_QUERY_DESCRIPTION', rail=args.rail,
                              query_hex=packet.hex(), port=PORTS[args.rail])))
        return
    import fcntl
    from mmio32 import WordAccess
    from servo_pwm_device import PwmDevice, Registers
    marker = json.loads(Path('/run/shadow-pwm-loaded.json').read_text())
    rail_info = marker.get('rail_uart', {})
    if (Path('/proc/sys/kernel/random/boot_id').read_text().strip() != args.boot_id or
            marker.get('boot_id') != args.boot_id or marker.get('sha256') != args.image_sha or
            marker.get('design_checks') != 'SERVO_IMAGE_DESIGN_CHECKS_PASS' or
            rail_info.get('design_checks') != 'RAIL_UART_DESIGN_CHECKS_PASS' or
            rail_info.get('baud') != 115200 or rail_info.get('format') != '8N1' or
            rail_info.get('ports') != PORTS):
        raise TelemetryError('Reviewed dual-UART boot/image/port manifest mismatch')
    # Hold the existing exclusive PWM lock so no servo client can arm concurrently.
    with open('/run/shadow-rail-uart.lock', 'a') as rail_lock:
        registers = Registers()
        try:
            fcntl.flock(rail_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            state = PwmDevice(registers).status()
            if (state['armed'] or state['enabled_mask'] or state['pending'] or state['faults'] or
                    state['sequence'] != args.expected_sequence):
                raise TelemetryError('Expected stopped PWM state does not match')
            fd = os.open('/dev/mem', os.O_RDWR | os.O_SYNC)
            try:
                with mmap.mmap(fd, 4096, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE,
                               offset=PORTS[args.rail]['base']) as memory:
                    words = WordAccess(memory)
                    port = QueryPort(words)
                    try:
                        result = port.request(args.address, args.query,
                                              checksum_mode=args.checksum_mode,
                                              firmware_kind=args.firmware_kind)
                    except Exception as error:
                        print('RAIL_QUERY_ERROR ' + json.dumps(dict(
                            rail=args.rail, error=str(error), reply_hex=port.received.hex(),
                            diagnostics=port.diagnostics(), motion_sent=False)), flush=True)
                        raise
                    finally:
                        words.close()
            finally:
                os.close(fd)
            after = PwmDevice(registers).status()
            if after != state:
                raise TelemetryError('PWM state changed during query')
            print('RAIL_QUERY ' + json.dumps(dict(rail=args.rail, result=result,
                  diagnostics=port.diagnostics(), pwm_unchanged=True, motion_sent=False)), flush=True)
        finally:
            registers.close()


if __name__ == '__main__':
    main()
