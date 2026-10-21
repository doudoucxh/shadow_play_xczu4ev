"""Host-only regression tests for Sony atomic-file replacement conflicts."""
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from run_v20_first_direction import FreshCamera, _read_camera_file


class Tests(unittest.TestCase):
    def setUp(self):
        from PIL import Image
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.session=self.root/'session';self.session.mkdir()
        (self.root/'current.json').write_text(json.dumps(dict(directory=str(self.session))))
        (self.session/'status.json').write_text(json.dumps(dict(state='streaming',frames=12,updated_unix_ms=100000)))
        data=io.BytesIO();Image.new('RGB',(8,8),(50,80,100)).save(data,format='JPEG')
        self.jpeg=data.getvalue();(self.session/'latest.jpg').write_bytes(self.jpeg)

    def test_brief_sharing_conflict_recovers_with_new_disk_read(self):
        real=Path.read_bytes;attempts=[]
        def read(path):
            if path.name=='latest.jpg':
                attempts.append(path)
                if len(attempts)==1:raise PermissionError('sharing violation')
            return real(path)
        with patch.object(Path,'read_bytes',read):
            result=FreshCamera(self.root,clock=lambda:100.1).sample()
        self.assertEqual(result['frame'],12);self.assertEqual(result['size'],[8,8])
        self.assertEqual(len(attempts),2)

    def test_persistent_denial_exits_within_bound_without_cached_frame(self):
        now=[0.]
        def sleep(t):now[0]+=t
        with patch.object(Path,'read_bytes',side_effect=PermissionError('persistent')), \
             patch('run_v20_first_direction.time.monotonic',side_effect=lambda:now[0]), \
             patch('run_v20_first_direction.time.sleep',side_effect=sleep):
            with self.assertRaises(PermissionError):_read_camera_file(self.session/'latest.jpg',binary=True)
        self.assertAlmostEqual(now[0],.15)

    def test_retry_cannot_turn_old_timestamp_into_fresh_frame(self):
        now=[101.49];real=Path.read_bytes;attempts=[0]
        def read(path):
            if path.name=='latest.jpg':
                attempts[0]+=1
                if attempts[0]==1:
                    now[0]=101.51
                    raise PermissionError('sharing violation')
            return real(path)
        with patch.object(Path,'read_bytes',read):
            with self.assertRaisesRegex(RuntimeError,'not streaming fresh'):
                FreshCamera(self.root,clock=lambda:now[0]).sample()

    def test_frozen_frame_and_corrupt_jpeg_still_rejected(self):
        now=[0.];camera=FreshCamera(self.root,clock=lambda:100.1,monotonic=lambda:now[0])
        camera.sample();now[0]=1.6
        with self.assertRaisesRegex(RuntimeError,'stalled'):camera.sample()
        (self.session/'latest.jpg').write_bytes(b'not a jpeg')
        with self.assertRaises(OSError):FreshCamera(self.root,clock=lambda:100.1).sample()


if __name__=='__main__':unittest.main()
