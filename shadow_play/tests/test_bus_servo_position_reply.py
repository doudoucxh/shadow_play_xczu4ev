"""Unpadded Servo.C feedback observed on ID10 during released hand teaching."""
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from shadow_play.bus_servo import protocol
from shadow_play.bus_servo.device import BusDevice
from shadow_play.bus_servo.model import Profile
from shadow_play.bus_servo.service import Controller
from shadow_play.tests.test_bus_servo_tiger import Registers
from shadow_play.tools.prepare_bus_console import build, CONSOLE_DIRECTORY

ROOT = Path(__file__).resolve().parents[2]
PROFILE = ROOT/'shadow_play/config/bus_servo.json'


class PositionReplyTests(unittest.TestCase):
    def test_real_id10_reply_and_all_valid_positions_padded_or_unpadded(self):
        # Exact RX captured on 2026-10-29, valid status 0 and UART faults 0.
        self.assertEqual(protocol.parse_reply(bytes.fromhex('233031305038333221'), 10, 'position'), 832)
        for value in range(500, 2501):
            for body in (str(value), f'{value:04d}'):
                self.assertEqual(protocol.parse_reply(f'#010P{body}!'.encode(), 10, 'position'), value)

    def test_invalid_replies_still_rejected(self):
        for body in ('499','0499','2501','99','00832','-832','+832','832.0',' 832','832 ',
                     'RAD','OK','0832T1000','ERR:3','832!#010P832'):
            with self.subTest(body=body), self.assertRaises((ValueError, protocol.ProtocolError)):
                protocol.parse_reply(f'#010P{body}!'.encode(),10,'position')
        for data in (b'#009P832!',b'#010P832',b'#010P83\xff!',b'#010P832!x'):
            with self.subTest(data=data), self.assertRaises(protocol.ProtocolError):
                protocol.parse_reply(data,10,'position')

    def test_ten_axis_probe_and_reads_crossing_1000_do_not_latch_failure(self):
        class FeedbackWire:
            def __init__(self, registers, offset, lock):
                self.offset, self.requests, self.position = offset, [], 832
            def exchange(self, data, expects_reply=True, reply_length=None):
                assert expects_reply
                self.requests.append(data)
                n = data[2] if data[:2] == b'\xff\xff' else int(data[1:4])
                assert self.offset == (256 if n <= 6 else 512)
                if data[:2] == b'\xff\xff':
                    assert data == protocol.health_request(n)
                    frame = bytes([n,3,0,0])
                    return b'\xff\xff'+frame+bytes([(~sum(frame))&255])
                prefix = f'#{n:03d}P'
                if data.endswith(b'VER!'): body = 'SERVO.C(7.3)'
                elif data.endswith(b'MOD!'): body = 'MOD1'
                elif data.endswith(b'RAD!'): body = str(self.position if n == 10 else 1500)
                else: raise AssertionError(data)
                return (prefix+body+'!').encode()

        profile = Profile.load(PROFILE)
        registers = Registers(profile.layout)
        with patch('shadow_play.bus_servo.device.WireBus', FeedbackWire):
            device = BusDevice(profile, registers)
            controller = Controller(profile, device, allow_release=True, allow_motion=True)
            seq = 0
            def execute(op, payload):
                nonlocal seq
                seq += 1
                return controller.execute(dict(seq=seq,op=op,payload=payload))
            try:
                rows = execute('probe',dict(numbers=list(range(1,11))))
                self.assertEqual(rows[10]['p'],832)
                for position in (999,1000,1001,998,832):
                    device.buses['tiger'].position = position
                    rows = execute('read',dict(numbers=list(range(1,11))))
                    self.assertEqual(rows[10]['p'],position)
                    self.assertEqual(set(rows),set(range(1,11)))
                self.assertFalse(device.failed)
                self.assertFalse(device.claimed)
                self.assertEqual(controller.verified,set(range(1,11)))
                execute('quit',{})
            finally:
                device.close()
            self.assertEqual(registers.writes,[])

    def test_generated_console_loads_correct_protocol_in_base_device(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/'console'
            manifest = build(PROFILE,out,allow_motion=True,service_overlay=True,protocol_overlay=True)
            self.assertTrue(manifest['protocol_overlay'])
            for name,digest in manifest['files'].items():
                self.assertEqual(hashlib.sha256((out/name).read_bytes()).hexdigest(),digest)
            script = (out/'start_console.sh').read_text(encoding='utf-8')
            verify = script.split("<<'VERIFY'\n",1)[1].split('\nVERIFY',1)[0]
            self.assertIn(manifest['files']['protocol.py'],verify)
            compile(verify,'console-verify','exec')
            # Execute the generated Python bootstrap in a fresh interpreter;
            # replace only main() with an inspector, so no hardware is opened.
            entry = script.split('exec python3 -u -c "',1)[1].split('" --profile',1)[0]
            entry = entry.replace(CONSOLE_DIRECTORY,out.as_posix())
            prefix,run = entry.split('runpy.run_path(',1)
            entry = prefix+'service = runpy.run_path('+run.replace("['main']()",'')
            entry += "; from shadow_play.bus_servo import device; assert device.protocol is protocol; "
            entry += f"from pathlib import Path; assert Path(device.protocol.__file__).resolve() == Path({str(out/'protocol.py')!r}).resolve(); "
            entry += "assert service['ServoUnavailable'] is protocol.ServoUnavailable; "
            entry += "assert device.protocol.parse_reply(b'#010P832!',10,'position') == 832; "
            entry += "print('OVERLAY_IMPORT_PASS')"
            result = subprocess.run([sys.executable,'-c',entry],cwd=ROOT,text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('OVERLAY_IMPORT_PASS',result.stdout)
            with self.assertRaises(ValueError):
                build(PROFILE,Path(tmp)/'invalid',protocol_overlay=True)


if __name__ == '__main__':
    unittest.main()
