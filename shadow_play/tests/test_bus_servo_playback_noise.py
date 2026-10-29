"""Noise filtering, bounded retiming and recoverable playback validation."""
import copy
from pathlib import Path
import queue
import threading
import unittest
from unittest.mock import patch

from shadow_play.bus_servo.device import SimulationDevice
from shadow_play.bus_servo.gui import Worker
from shadow_play.bus_servo.model import Profile, new_recording, playback_plan
from shadow_play.bus_servo.session import TeachingSession, PlaybackRejected
from shadow_play.bus_servo.timeline import PlaybackTimeline


PROFILE = Path(__file__).resolve().parents[1]/'config/bus_servo.json'


class PlaybackNoiseTests(unittest.TestCase):
    def setUp(self):self.profile=Profile.load(PROFILE)

    def record(self, positions, interval=.02):
        record=new_recording(self.profile,[1,7],True,20)
        for i,p in enumerate(positions):
            record['samples'].append({'t':i*interval,'positions':{'1':1500,'7':p},
                                      'axis_t':{'1':i*interval,'7':i*interval}})
        record['complete']=True
        return record

    def test_stationary_jitter_is_held_without_changing_source(self):
        record=self.record([1500,1503,1497,1502,1498,1500])
        original=copy.deepcopy(record)
        plan=playback_plan(record,self.profile,[1,7],1)
        self.assertTrue(all(targets['7']==1500 for _,targets,_ in plan))
        self.assertEqual(plan.retimed_intervals,0)
        self.assertEqual(plan.filtered_samples,4)
        self.assertEqual(record,original)

    def test_gradual_movement_accumulates_beyond_deadband(self):
        plan=playback_plan(self.record(list(range(1500,1521))),self.profile,[7],1)
        self.assertEqual([targets['7'] for _,targets,_ in plan[:4]],[1500,1500,1500,1504])
        self.assertEqual(plan[-1][1]['7'],1520)

    def test_fast_interval_is_extended_for_all_selected_axes(self):
        record=self.record([1500,1800,1800],.1)
        original=copy.deepcopy(record)
        plan=playback_plan(record,self.profile,[1,7],.5)
        self.assertEqual(plan[0][2],1350)
        self.assertEqual(plan[1][0],1.35)
        self.assertEqual(plan[1][2],200)
        self.assertEqual(plan.retimed_intervals,1)
        self.assertEqual(set(plan[0][1]),{'1','7'})
        before={'1':1500,'7':1500}
        for _,targets,ms in plan:
            for key,p in targets.items():
                axis=self.profile.axes[int(key)]
                self.assertLessEqual(abs(axis.degrees(p)-axis.degrees(before[key]))/(ms/1000),axis.max_speed+1e-8)
            before=targets
        self.assertEqual(record,original)
        # Mapping is local, not elapsed multiplied by the requested speed.
        timeline=PlaybackTimeline(record,.5,plan=plan)
        p=timeline.snapshot(.675,'playing')
        self.assertAlmostEqual(p['source_s'],.05)
        self.assertAlmostEqual(p['duration_s'],1.55)
        self.assertAlmostEqual(p['fraction'],.675/1.55)
        self.assertAlmostEqual(timeline.snapshot(1.45,'playing')['source_s'],.15)

    def test_subset_does_not_slow_for_an_unselected_axis(self):
        plan=playback_plan(self.record([1500,1800],.1),self.profile,[1],.5)
        self.assertEqual(plan[0][2],200)
        self.assertEqual(plan.retimed_intervals,0)
        self.assertEqual(plan[0][1],{'1':1500})

    def test_bad_material_is_rejected_before_feedback_or_motion(self):
        device=SimulationDevice(self.profile)
        session=TeachingSession(self.profile,device,'.')
        record=self.record([1500,1501]);record['complete']=False
        with patch.object(device,'read',side_effect=AssertionError('unexpected read')), \
                patch.object(device,'move') as move,patch.object(device,'stop') as stop:
            with self.assertRaises(PlaybackRejected):session.start_playback(record,[7])
            move.assert_not_called();stop.assert_not_called()
        self.assertFalse(session.playing)

    def test_worker_preflight_rejection_keeps_session_and_feedback(self):
        record=self.record([1500,1501]);record['complete']=False
        commands,events,stop=queue.Queue(),queue.Queue(),threading.Event()
        worker=Worker(commands,events,stop);worker.start()
        try:
            commands.put(('connect',(self.profile,True,'unused')))
            while events.get(timeout=2)[0]!='connected':pass
            session=worker.session
            with patch.object(session.device,'stop') as stopped:
                commands.put(('play',(record,[7],.5)))
                seen=[]
                while not seen or seen[-1][0]!='command_done':seen.append(events.get(timeout=2))
                self.assertIn('playback_rejected',[kind for kind,_ in seen])
                self.assertNotIn('error',[kind for kind,_ in seen])
                self.assertIs(worker.session,session)
                self.assertIn(7,session.ready_axes)
                self.assertFalse(session.playing)
                stopped.assert_not_called()
        finally:
            commands.put(('shutdown',None));worker.join(timeout=2)
        self.assertFalse(worker.is_alive())

    def test_range_and_source_checks_are_still_enforced(self):
        record=self.record([1500,2499])
        with self.assertRaises(ValueError):playback_plan(record,self.profile,[7],.5)
        record=self.record([1500,1501]);record['profile_sha256']='different'
        with self.assertRaises(ValueError):playback_plan(record,self.profile,[7],.5)


if __name__=='__main__':unittest.main()
