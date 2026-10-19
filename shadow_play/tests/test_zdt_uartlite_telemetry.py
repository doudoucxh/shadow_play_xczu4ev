from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from zdt_readonly_protocol import ProtocolError
from zdt_uartlite_telemetry import QueryPort, TelemetryError


class Fake:
    def __init__(self, reply=b'\x01\x3a\x83\x6b', *, status=4):
        self.now = 0.
        self.reply = bytearray(reply)
        self.writes = []
        self.initial_status = status

    def clock(self):
        return self.now

    def sleep(self, delta):
        self.now += delta

    def read(self, offset):
        if offset == 8:
            if len(self.writes) < 3:
                return self.initial_status
            return 4 | bool(self.reply)
        if offset == 0:
            return self.reply.pop(0)
        raise AssertionError(offset)

    def write(self, offset, value):
        self.writes.append((offset, value))


def request(fake, kind='status', firmware='Emm'):
    port = QueryPort(fake, clock=fake.clock, sleep=fake.sleep)
    result = port.request(1, kind, checksum_mode='fixed_6b', firmware_kind=firmware)
    return port, result


class Tests(unittest.TestCase):
    def test_only_complete_query_at_tx_register_and_no_reset(self):
        f = Fake()
        p, r = request(f)
        self.assertEqual(f.writes, [(4, 1), (4, 0x3a), (4, 0x6b)])
        self.assertTrue(r['freshness_verified'])
        with self.assertRaises(TelemetryError):
            p.request(1, 'status', checksum_mode='fixed_6b', firmware_kind='Emm')
        self.assertEqual(len(f.writes), 3)

    def test_stale_data_pending_tx_or_errors_never_transmit(self):
        for status in (0, 1, 5, 6, 12, 0x14, 0x24, 0x44, 0x84):
            f = Fake(status=status)
            with self.assertRaises(TelemetryError):
                request(f)
            self.assertEqual(f.writes, [])

    def test_timeout_does_not_retry_or_reset(self):
        f = Fake(reply=b'')
        with self.assertRaises(TelemetryError):
            request(f)
        self.assertEqual(len(f.writes), 3)
        self.assertLess(f.now, .371)

    def test_malformed_or_extra_reply_rejects(self):
        for raw in (b'\x02\x3a\x83\x6b', b'\x01\x3a\x83\x6b\x00', b'\x00' * 17):
            with self.assertRaises((ProtocolError, TelemetryError)):
                request(Fake(raw))

    def test_invalid_or_motion_request_sends_nothing(self):
        for kind, fw in (('move', 'Emm'), ('position', None)):
            f = Fake()
            with self.assertRaises((ProtocolError, TelemetryError)):
                request(f, kind, fw)
            self.assertEqual(f.writes, [])


if __name__ == '__main__':
    unittest.main()
