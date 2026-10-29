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
        self.assertFalse(data['hardware_verified'])
        self.assertFalse(data['mechanical_limits_verified'])
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

    def test_build_refuses_absent_confirmation_or_added_motion_flags(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            for key,value in [('electrical_3v3_verified',False),('hardware_verified',True),
                              ('mechanical_limits_verified',True),('electrical_verification',{})]:
                data=json.loads(PROFILE.read_text(encoding='utf-8'))
                data[key]=value
                source=base/'profile.json'
                source.write_text(json.dumps(data),encoding='utf-8')
                with self.assertRaises(ValueError): build(source,base/'must-not-exist')
                self.assertFalse((base/'must-not-exist').exists())


if __name__=='__main__': unittest.main()
