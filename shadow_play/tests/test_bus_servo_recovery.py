"""Reviewed stopped segments preserve source evidence and reject corrupt frames."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from shadow_play.bus_servo.model import Profile, validate_recording, playback_plan, save_recording
from shadow_play.bus_servo.recovery import recover_file, digest
from shadow_play.bus_servo.av_editing import AVProject, compile_motion
from shadow_play.tests.test_bus_servo import recording

PROFILE=Path(__file__).resolve().parents[1]/'config/bus_servo.json'


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.profile=Profile.load(PROFILE)
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'stopped.json'
        self.source=recording(self.profile,simulation=False)
        self.source.update(complete=False,end_reason='operator_stopped')
    def tearDown(self):self.temp.cleanup()
    def write(self,source=None):
        self.path.write_text(json.dumps(source or self.source),encoding='utf-8')
        return self.path.read_bytes()

    def test_recovers_only_retained_frames_without_overwriting_or_relabeling_source(self):
        before=self.write();out=recover_file(self.path,self.profile)
        validate_recording(out,self.profile,live=True)
        self.assertEqual(self.path.read_bytes(),before)
        self.assertEqual(out['recovery']['source_record'],self.source)
        self.assertFalse(out['recovery']['source_record']['complete'])
        self.assertEqual(out['mode'],'recovered_operator_stop')
        self.assertEqual([r['positions'] for r in out['samples']],[r['positions'] for r in self.source['samples']])
        self.assertEqual(len(playback_plan(out,self.profile,[1,7],1)),4)
        path=Path(self.temp.name)/'reviewed.motion.json';save_recording(path,out)
        with self.assertRaises(FileExistsError):save_recording(path,out)

    def test_original_still_rejected_with_actionable_reason(self):
        with self.assertRaisesRegex(ValueError,'② 结束录制'):
            validate_recording(self.source,self.profile)
        self.assertFalse(self.source['complete'])

    def test_fault_disconnect_recording_or_already_complete_not_auto_recovered(self):
        for reason in ('feedback timeout','connection_closed','recording','operator_finished'):
            bad=copy.deepcopy(self.source);bad['end_reason']=reason;self.write(bad)
            with self.assertRaises(ValueError):recover_file(self.path,self.profile)
        bad=copy.deepcopy(self.source);bad['complete']=True;self.write(bad)
        with self.assertRaises(ValueError):recover_file(self.path,self.profile)

    def test_missing_axes_range_time_origin_gap_and_per_axis_reversal_rejected(self):
        for kind in ('axis','range','time','origin','gap','axis_time'):
            bad=copy.deepcopy(self.source)
            if kind=='axis':del bad['samples'][1]['positions']['7']
            elif kind=='range':bad['samples'][1]['positions']['7']=2499
            elif kind=='time':bad['samples'][1]['t']=0
            elif kind=='origin':
                for row in bad['samples']:
                    row['t']+=1;row['axis_t']={k:v+1 for k,v in row['axis_t'].items()}
            elif kind=='gap':
                for row in bad['samples'][2:]:
                    row['t']+=1;row['axis_t']={k:v+1 for k,v in row['axis_t'].items()}
            else:bad['samples'][2]['axis_t']['1']=.05
            self.write(bad)
            with self.subTest(kind=kind),self.assertRaises(ValueError):recover_file(self.path,self.profile)

    def test_derived_samples_or_embedded_source_tampering_fails(self):
        self.write();out=recover_file(self.path,self.profile)
        for kind in ('sample','source','fake_complete','mode'):
            bad=copy.deepcopy(out)
            if kind=='sample':bad['samples'][1]['positions']['7']+=1
            elif kind=='source':bad['recovery']['source_record']['samples'][1]['positions']['7']+=1
            elif kind=='mode':bad['mode']='recorded_normally'
            else:
                bad['recovery']['source_record']['complete']=True
                bad['recovery']['source_content_sha256']=digest(bad['recovery']['source_record'])
            with self.subTest(kind=kind),self.assertRaises(ValueError):validate_recording(bad,self.profile)

    def test_simulated_recovery_never_becomes_hardware_material(self):
        self.source['source']='simulation';self.write();out=recover_file(self.path,self.profile)
        self.assertEqual(out['source'],'simulation')
        with self.assertRaisesRegex(ValueError,'Simulation'):validate_recording(out,self.profile,live=True)

    def test_checked_segment_can_be_used_in_joint_audio_motion_editor(self):
        self.write();out=recover_file(self.path,self.profile)
        project=AVProject(self.profile,[1,7]);project.add_motion(out)
        combined=compile_motion(project.data,self.profile)
        validate_recording(combined,self.profile,live=True)
        self.assertEqual(combined['source'],'edited_feedback')


if __name__=='__main__':unittest.main()
