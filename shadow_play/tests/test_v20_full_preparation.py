import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import v20_full_preparation as model


def fixture():
    plan=dict(schema='task1_choreography_editor_v3',motor_ready=False,
        audio=dict(duration_s=1,sample_rate_hz=1000,sample_frames=1000),
        scenes=[dict(id='S00',start_s=0,end_s=.4,title='first'),dict(id='S01',start_s=.4,end_s=1,title='second')],
        impact_cues=[dict(id='P14',time_s=.72,preview_lead_s=.3),dict(id='P15',time_s=.6,preview_lead_s=.3)],
        narration_segments=[],attack_groups=[],v20_additions={},mechanism_contract={},
        arbitrary_original_field=dict(preserve='original'))
    frames=[];rods=[]
    for index in range(25):
        t=index/25;scene='S00' if t<.4 else 'S01'
        marker='P15' if index==15 else 'P14' if index==18 else None
        points={name:[.2,.4] for name in model.POINTS.values()}
        frames.append(dict(time_s=t,scene_id=scene,phase='visual',motor_ready=False,
            units='normalized_screen_xy',origin='bottom_left',puppet_attachment_points=copy.deepcopy(points),
            rod_endpoints_illustrative=copy.deepcopy(points),visible=dict(wusong=1,tiger=1),
            impact_id=marker,body_centers=dict(wusong=[.2,.2],tiger=[.7,.2]),relative_depth_state={},holding_hand=None))
        rods.append(dict(time_s=t,scene_id=scene,motor_ready=False,five_rods={name:dict(
            target_front_attachment_xy=[.2,.4],illustrative_tip_xy=[.2,.4],command=None,rear_observation_xy=None) for name in model.RODS}))
    return plan,frames,rods


class Tests(unittest.TestCase):
    def setUp(self):self.plan,self.frames,self.rods=fixture()
    def validate(self):return model.validate_structure(self.plan,self.frames,self.rods,expected_scenes=2,expected_cues=2)

    def test_contiguous_score_and_exact_terminal_audio_sample(self):
        self.validate();score=model.compile_score(self.plan,self.frames)
        refs=model.compile_references(self.frames,1,1000)
        self.assertEqual(refs[-1]['audio_sample'],1000)
        self.assertTrue(refs[-1]['visual_endpoint_hold'])
        self.assertTrue(all(f['motor_command'] is None and f['rail_command'] is None and f['motor_ready'] is False for f in refs))
        self.assertFalse(score['motor_ready'])

    def test_ids_follow_time_and_preview_lead_never_becomes_motor_lead(self):
        score=model.compile_score(self.plan,self.frames)
        self.assertEqual([c['id'] for c in score['impact_cues']],['P15','P14'])
        for cue in score['impact_cues']:
            self.assertEqual(cue['target_audio_sample'],round(cue['time_s']*1000))
            self.assertIsNone(cue['measured_motor_lead_s'])
            self.assertIsNone(cue['motor_send_audio_sample'])
        self.assertEqual(score['source_choreography'],self.plan)
        self.assertTrue(all(s['reset_pose_at_boundary'] is False for s in score['scenes']))

    def test_gaps_overlap_bad_duration_and_duplicate_cues_reject(self):
        for field,value in [('start_s',.41),('start_s',.39),('end_s',.4)]:
            original=copy.deepcopy(self.plan);self.plan['scenes'][1][field]=value
            with self.assertRaises(ValueError):self.validate()
            self.plan=original
        self.plan['audio']['duration_s']=1.1
        with self.assertRaises(ValueError):self.validate()
        self.plan=fixture()[0];self.plan['impact_cues'][1]['id']='P14'
        with self.assertRaises(ValueError):self.validate()

    def test_wrong_clock_units_missing_rod_and_injected_commands_reject(self):
        cases=[lambda:self.frames[3].update(time_s=.13),lambda:self.frames[3].update(units='mm'),
               lambda:self.rods[3]['five_rods'].pop('TT'),
               lambda:self.rods[3]['five_rods']['WH'].update(command=[1500,1500]),
               lambda:self.rods[3]['five_rods']['WH'].update(rear_observation_xy=[0,0]),
               lambda:self.frames[3]['puppet_attachment_points'].update(wusong_head=[float('nan'),0]),
               lambda:self.plan.update(motor_ready=True)]
        for change in cases:
            self.plan,self.frames,self.rods=fixture();change()
            with self.assertRaises(ValueError):self.validate()

    def test_bad_marker_and_cue_outside_audio_reject(self):
        self.frames[15]['impact_id']='P14'
        with self.assertRaises(ValueError):model.compile_score(self.plan,self.frames)
        self.plan['impact_cues'][0]['time_s']=1
        with self.assertRaises(ValueError):self.validate()

    def test_endpoint_is_last_scene_without_reset(self):
        self.assertEqual(model.scene_at(self.plan['scenes'],.4)['id'],'S01')
        self.assertEqual(model.scene_at(self.plan['scenes'],1)['id'],'S01')
        with self.assertRaises(ValueError):model.scene_at(self.plan['scenes'],1.1)
        for t in [-1,float('nan'),float('inf')]:
            with self.assertRaises(ValueError):model.sample_at(t,44100)

    def test_source_and_playback_sample_clocks_are_separate(self):
        playback=dict(sample_rate_hz=48000,decoded_frames=48000,sha256='a'*64)
        score=model.compile_score(self.plan,self.frames,playback)
        cue=score['impact_cues'][0]
        self.assertEqual(cue['target_audio_sample'],600)
        self.assertEqual(cue['target_playback_sample'],28800)
        self.assertIsNone(score['playback_clock']['acoustic_latency_s'])

    def test_readiness_cannot_map_tail_to_feet_or_unlock_from_flags(self):
        evidence=dict(state=dict(armed=False,enabled_mask=0,faults=0,pending=False,sequence=12665),
            boot_id='historical',observed_clear_response_channels=list(range(1,11)),
            operator_confirmed_control_groups={'9/10':'Tiger feet'},physical_performance_ready=True)
        result=model.readiness(evidence,dict(rails={'rail1':{'hardware_verified':True}}))
        self.assertFalse(result['physical_performance_ready'])
        self.assertFalse(result['physical_execution_entry_available'])
        self.assertIsNone(result['source_TT_channel_assignment'])
        self.assertIn('tiger_attachment_conflict',[b['id'] for b in result['blockers']])

    def test_manifest_checks_hash_size_duplicates_and_traversal(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);content=b'unchanged';(root/'data.txt').write_bytes(content)
            manifest=[dict(path='data.txt',bytes=len(content),sha256=hashlib.sha256(content).hexdigest())]
            model.write_json(root/'文件清单与校验值.json',manifest)
            self.assertEqual(model.verify_manifest(root)['files_checked'],1)
            (root/'data.txt').write_bytes(b'corrupted')
            with self.assertRaises(ValueError):model.verify_manifest(root)
            (root/'data.txt').write_bytes(content);model.write_json(root/'文件清单与校验值.json',manifest*2)
            with self.assertRaises(ValueError):model.verify_manifest(root)
            for path in ['../outside','/absolute','C:/outside','folder\\outside','']:
                with self.assertRaises(ValueError):model.contained(root,path)

    def test_json_nonfinite_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'bad.json';path.write_text('{"time":NaN}',encoding='utf-8')
            with self.assertRaises(ValueError):model.load(path)

    def test_package_text_uses_canonical_lf_across_platforms(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'canonical.json';model.write_json(path,dict(chinese='备份一致'))
            self.assertNotIn(b'\r\n',path.read_bytes())
        for name in (*model.OUTPUT_FILES,'MANIFEST.json'):
            self.assertNotIn(b'\r\n',(model.OUTPUT/name).read_bytes(),name)


if __name__=='__main__':unittest.main()
