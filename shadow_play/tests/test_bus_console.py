import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from shadow_play.bus_servo.model import Profile
from shadow_play.tools.prepare_bus_console import build, BASE_DIRECTORY, BASE_MANIFEST_SHA, CONSOLE_DIRECTORY

PROFILE=Path(__file__).resolve().parents[1]/'config/bus_servo.json'


class ConsoleTests(unittest.TestCase):
    def test_confirmed_profile_keeps_recording_identity_and_limits(self):
        data=json.loads(PROFILE.read_text(encoding='utf-8'))
        before=dict(data,electrical_3v3_verified=False)
        self.assertEqual(Profile(data).fingerprint,Profile(before).fingerprint)
        self.assertTrue(data['electrical_3v3_verified'])
        self.assertTrue(data['hardware_verified'])
        self.assertTrue(data['mechanical_limits_verified'])
        self.assertEqual(data['motion_verification']['source'],'user_report')
        self.assertEqual(Profile(data).layout.board_directory,Path(CONSOLE_DIRECTORY).name)

    def test_build_pins_runtime_and_profile_without_motion_permission(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'console'
            manifest=build(PROFILE,out)
            for name,sha in manifest['files'].items():
                self.assertEqual(hashlib.sha256((out/name).read_bytes()).hexdigest(),sha)
            script=(out/'start_console.sh').read_text(encoding='utf-8')
            self.assertIn(BASE_DIRECTORY,script)
            self.assertIn(BASE_MANIFEST_SHA,script)
            self.assertIn('--allow-release',script)
            self.assertNotIn('--allow-motion',script)
            self.assertNotIn('fpgautil',script)
            self.assertNotIn('systemctl',script)
            python=script.split("<<'VERIFY'\n",1)[1].split('\nVERIFY',1)[0]
            compile(python,'console-verify','exec')
            with self.assertRaises(FileExistsError): build(PROFILE,out)

    def test_build_refuses_absent_electrical_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            for key,value in [('electrical_3v3_verified',False),('electrical_verification',{})]:
                data=json.loads(PROFILE.read_text(encoding='utf-8'))
                data[key]=value
                source=base/'profile.json'
                source.write_text(json.dumps(data),encoding='utf-8')
                with self.assertRaises(ValueError): build(source,base/'must-not-exist')
                self.assertFalse((base/'must-not-exist').exists())

    def test_motion_requires_opt_in_all_checks_and_user_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            manifest=build(PROFILE,base/'enabled',allow_motion=True)
            self.assertTrue(manifest['allow_motion'])
            script=(base/'enabled/start_console.sh').read_text(encoding='utf-8')
            self.assertEqual(script.count('--allow-motion'),1)
            for key,value in [('hardware_verified',False),('mechanical_limits_verified',False),
                              ('motion_verification',{}),('hardware_verified',1)]:
                data=json.loads(PROFILE.read_text(encoding='utf-8'));data[key]=value
                source=base/'profile.json';source.write_text(json.dumps(data),encoding='utf-8')
                with self.assertRaises(ValueError):build(source,base/'must-not-exist',allow_motion=True)
                self.assertFalse((base/'must-not-exist').exists())

    def test_enabling_motion_does_not_make_board_handshake_transmit(self):
        from unittest.mock import patch
        from shadow_play.bus_servo.device import BusDevice
        from shadow_play.bus_servo.service import Controller
        from shadow_play.tests.test_bus_servo_tiger import Registers, ServoWire
        profile=Profile.load(PROFILE);registers=Registers(profile.layout)
        with patch('shadow_play.bus_servo.device.WireBus',ServoWire):
            device=BusDevice(profile,registers)
            controller=Controller(profile,device,allow_motion=True,allow_release=True)
            try:
                hello=controller.execute(dict(seq=1,op='hello',payload={}))
                self.assertTrue(hello['motion_allowed']);self.assertTrue(hello['release_allowed'])
                controller.execute(dict(seq=2,op='status',payload={}))
                controller.execute(dict(seq=3,op='quit',payload={}))
            finally:device.close()
            self.assertEqual(registers.writes,[])
            self.assertTrue(all(not bus.requests for bus in device.buses.values()))


if __name__=='__main__': unittest.main()
