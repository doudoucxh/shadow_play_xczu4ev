"""Run the image-only CLI against an independent rectangular reference."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

PROGRAM = None


class StaticGeometryTests(unittest.TestCase):
    def setUp(self):
        if PROGRAM is None:
            self.skipTest('Supply stage_reference executable as the first CLI argument')
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.image = self.root/'frame.ppm'
        self.image.write_bytes(b'P6\n160 110\n255\n' + bytes([180,180,180])*160*110)
        self.spec = dict(version=1, reference_view='front', width_mm=400, height_mm=200,
                         image_width=160, image_height=110,
                         reference_pixels=[[20,80],[120,80],[120,20],[20,20]],
                         points=[dict(id='middle',pixel=[70,50])])
        self.output = self.root/'result'

    def run_cli(self):
        source=self.root/'reference.json';source.write_text(json.dumps(self.spec))
        return subprocess.run([PROGRAM,str(source),str(self.image),str(self.output)],
                              capture_output=True,text=True)

    def test_metric_axes_and_never_produces_motor_calibration(self):
        result=self.run_cli();self.assertEqual(result.returncode,0,result.stderr)
        data=json.loads((self.output/'geometry.json').read_text())
        x,y=data['points'][0]['stage_mm']
        self.assertAlmostEqual(x,200,places=3);self.assertAlmostEqual(y,100,places=3)
        self.assertIs(data['metric_accuracy_verified'],False)
        self.assertIs(data['motion_calibration_ready'],False)
        self.assertIsNone(data['actual_servo_state'])
        self.assertTrue((self.output/'stage_preview.png').is_file())
        self.assertAlmostEqual((data['preview_width']-1)/(data['preview_height']-1),2.0,places=3)

    def test_crossed_corners_and_outside_points_reject_before_output(self):
        self.spec['reference_pixels'][1],self.spec['reference_pixels'][2]=self.spec['reference_pixels'][2],self.spec['reference_pixels'][1]
        self.assertNotEqual(self.run_cli().returncode,0);self.assertFalse(self.output.exists())
        self.spec['reference_pixels'][1],self.spec['reference_pixels'][2]=self.spec['reference_pixels'][2],self.spec['reference_pixels'][1]
        self.spec['points'][0]['pixel']=[140,50]
        self.assertNotEqual(self.run_cli().returncode,0);self.assertFalse(self.output.exists())

    def test_measured_inset_markers_are_not_treated_as_full_stage_corners(self):
        self.spec['reference_points_mm']=[[10,20],[390,20],[390,180],[10,180]]
        self.spec['points']=[dict(id='lower_left_quarter',pixel=[45,65])]
        result=self.run_cli();self.assertEqual(result.returncode,0,result.stderr)
        data=json.loads((self.output/'geometry.json').read_text())
        x,y=data['points'][0]['stage_mm']
        self.assertAlmostEqual(x,105,places=3);self.assertAlmostEqual(y,60,places=3)
        self.assertEqual(data['reference_points_mm'],self.spec['reference_points_mm'])

    def test_bad_physical_references_reject(self):
        for mm in ([[10,20],[390,20],[390,180]],
                   [[10,20],[390,180],[390,20],[10,180]],
                   [[10,20],[410,20],[410,180],[10,180]]):
            self.spec['reference_points_mm']=mm
            self.assertNotEqual(self.run_cli().returncode,0)
            self.assertFalse(self.output.exists())

    def test_frame_change_and_existing_evidence_are_not_accepted(self):
        self.spec['image_width']=161
        self.assertNotEqual(self.run_cli().returncode,0);self.assertFalse(self.output.exists())
        self.spec['image_width']=160
        self.assertEqual(self.run_cli().returncode,0)
        saved=(self.output/'geometry.json').read_bytes()
        self.assertNotEqual(self.run_cli().returncode,0)
        self.assertEqual((self.output/'geometry.json').read_bytes(),saved)


if __name__=='__main__':
    if len(sys.argv)<2:
        raise SystemExit('Usage: test_stage_reference.py STAGE_REFERENCE_EXECUTABLE')
    PROGRAM = str(Path(sys.argv.pop(1)).resolve())
    unittest.main()
