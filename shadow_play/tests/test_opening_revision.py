"""Task-space authoring checks; no physical motion certification."""
import json
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import build_opening_revision as s

class OpeningTests(unittest.TestCase):
    def setUp(self):
        self.base=json.loads((s.OUT/'score.json').read_text(encoding='utf-8'))
        self.observed=json.loads((ROOT/'config/person_head_centering_fine_result.20261015.json').read_text())
        self.rev,self.score=s.build(self.base,self.observed)
    def test_audio_and_later_scene_evidence_preserved(self):
        self.assertEqual(self.score['audio'],self.base['audio'])
        self.assertEqual(self.score['impact_cues'],self.base['impact_cues'])
        self.assertEqual(self.score['scenes'][10:],self.base['scenes'][10:])
        for x in self.score['scenes'][5:10]:
            self.assertEqual(x['execution_status'],'planned_not_executed')
            self.assertIn('previous_version_execution',x)
    def test_no_motor_mapping_fabricated(self):
        self.assertFalse(self.rev['motor_ready'])
        self.assertIsNone(self.rev['servo_keyframes_us'])
        self.assertIsNone(self.rev['head_reference']['startup_command'])
        self.assertIsNone(self.rev['dialogue']['exact_word_timing_s'])
        self.assertFalse(self.rev['slide_rail']['enabled'])
        self.assertIsNone(self.rev['slide_rail']['commands'])
        self.assertEqual(self.rev['head_reference']['last_command_us'][2:4],[1565,1554])
    def test_hip_hand_tracks_body_during_pointing(self):
        for row in self.rev['keyframes']:
            if 17.4<=row['time_s']<=22.5:
                self.assertAlmostEqual(row['left_hand'][0],-.22)
                self.assertAlmostEqual(row['left_hand'][1]-row['body_lift'],.12)
        points=[r for r in self.rev['keyframes'] if '指点重音' in r['action']]
        self.assertEqual(len(points),3)
        self.assertGreater(points[1]['right_hand'][1],points[0]['right_hand'][1])
    def test_hip_arc_has_continuous_nonzero_interior_speed(self):
        rows=self.rev['keyframes']; samples=[s.sample(rows,16.8+i*.001) for i in range(601)]
        c=s.HIP_ARC['center'];r=s.HIP_ARC['radius']
        for p in samples:
            x,y=p['left_hand']
            self.assertAlmostEqual((x-c[0])**2+(y-c[1])**2,r*r)
            self.assertEqual(p['head'],[0,1])
            self.assertEqual(p['right_hand'],[.30,.45])
        for p,q in zip(samples[1:-1],samples[2:]):
            self.assertGreater(q['left_hand'][0],p['left_hand'][0])
        for t in (16.9,17.0,17.1,17.2,17.3):
            a=s.sample(rows,t-.00001)['left_hand'];b=s.sample(rows,t)['left_hand'];c=s.sample(rows,t+.00001)['left_hand']
            self.assertGreater(b[0]-a[0],1e-6)
            self.assertAlmostEqual(b[0]-a[0],c[0]-b[0],places=7)
        self.assertIsNone(self.rev['hip_entry']['pwm_route'])
    def test_continuous_centered_head_and_defined_endpoints(self):
        rows=self.rev['keyframes']
        self.assertTrue(all(a['time_s']<b['time_s'] for a,b in zip(rows,rows[1:])))
        for row in rows:
            sampled=s.sample(rows,row['time_s'])
            self.assertEqual(sampled['head'][0],0)
            for k in sampled:
                for a,b in zip(sampled[k],row[k]):self.assertAlmostEqual(a,b)
        self.assertEqual(s.sample(rows,0),s.sample(rows,10))
        self.assertEqual(s.sample(rows,67),s.sample(rows,29))
    def test_component_candidates_keep_head_yaw_and_low_hand_margin(self):
        for p in self.rev['component_command_candidates']['poses']:
            self.assertFalse(p['executed'])
            self.assertEqual(p['person_us'][2],1565)
            self.assertGreaterEqual(p['person_us'][1],1212)
        self.assertTrue(all(r['body_lift']>=0 for r in self.rev['keyframes']))
    def test_partial_trial_does_not_certify_hip_arc_or_rise(self):
        result=json.loads((ROOT/'config/person_opening_m_result.20261015.json').read_text(encoding='utf-8'))
        rev,score=s.build(self.base,self.observed,result)
        self.assertEqual([p['executed'] for p in rev['component_command_candidates']['poses']],[True,True,True,False])
        self.assertEqual(rev['hip_entry']['status'],'planned_not_executed')
        self.assertFalse(score['motor_ready'])

if __name__=='__main__':unittest.main()
