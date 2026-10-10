import io
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from PIL import Image, ImageDraw

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/calibration'))
from camera_bridge import SonySource, check_jpeg


def jpeg(blank=False):
    image=Image.new('RGB',(64,64),(0,255,0))
    if not blank: ImageDraw.Draw(image).rectangle((5,5,30,30), fill=(50,20,100))
    buffer=io.BytesIO(); image.save(buffer,format='JPEG'); return buffer.getvalue()


class CameraTests(unittest.TestCase):
    def test_green_frame_and_bad_payload_rejected(self):
        with self.assertRaises(ValueError): check_jpeg(jpeg(True))
        with self.assertRaises(Exception): check_jpeg(b'not a jpeg')
        self.assertEqual(check_jpeg(jpeg()),jpeg())

    def test_source_age_state_and_path(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); session=root/'session-test'; session.mkdir()
            (root/'current.json').write_text(json.dumps({'directory':str(session)}))
            (session/'latest.jpg').write_bytes(jpeg())
            state={'updated_unix_ms':time.time()*1000,'state':'streaming','frames':6}
            status=session/'status.json'
            status.write_text(json.dumps(state)); source=SonySource(root)
            frame,identity,age,stamp=source.read()
            self.assertEqual(identity,'session-test-6'); self.assertLess(age,1500)
            self.assertTrue(stamp.endswith('+00:00')); self.assertTrue(frame)
            state['updated_unix_ms']-=3000; status.write_text(json.dumps(state))
            with self.assertRaises(ValueError): source.read()
            state.update(updated_unix_ms=time.time()*1000,state='stopped'); status.write_text(json.dumps(state))
            with self.assertRaises(ValueError): source.read()
            (root/'current.json').write_text(json.dumps({'directory':str(root.parent)}))
            with self.assertRaises(ValueError): source.read()


if __name__=='__main__': unittest.main()
