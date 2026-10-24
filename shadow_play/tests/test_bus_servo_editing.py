"""Editing preserves evidence, timing and live/simulation boundaries."""
import copy
import json
from pathlib import Path
import tempfile
import queue
import threading
import time
import unittest

from shadow_play.bus_servo.editing import EditProject, PoseCaptureError, capture_pose, compile_project
from shadow_play.bus_servo.model import Profile, new_recording, validate_recording, playback_plan, save_recording
from shadow_play.bus_servo.device import SimulationDevice
from shadow_play.bus_servo.session import TeachingSession

PROFILE = Path(__file__).resolve().parents[1]/'config/bus_servo.json'


def take(profile, simulated=True, numbers=None):
    numbers = numbers or [1, 7]
    r = new_recording(profile, numbers, simulated, 10)
    for i in range(21):
        r['samples'].append({'t': i*.1, 'positions': {str(n): 1500+i*5 for n in numbers},
                             'axis_t': {str(n): i*.1 for n in numbers}})
    r['complete'] = True
    return r


class EditingTests(unittest.TestCase):
    def setUp(self):
        self.profile = Profile.load(PROFILE)
        self.project = EditProject(self.profile, [1, 7])

    def pose(self, p, simulated=True):
        return capture_pose(self.profile, [1, 7], {n: {'p': p, 'at': 10+n*.001} for n in [1, 7]}, simulated)

    def test_capture_reads_actual_position_without_any_motion(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = SimulationDevice(self.profile); s = TeachingSession(self.profile, d, tmp)
            d.positions[1] = 1550
            pose = s.capture_pose([1, 7])
            self.assertEqual(pose['positions'], {'1': 1550, '7': 1500})
            self.assertEqual(d.motions, {}); self.assertEqual(d.released, set())
            s.close()

    def test_capture_rejects_recording_and_incomplete_feedback(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = TeachingSession(self.profile, SimulationDevice(self.profile), tmp)
            s.start_recording([1])
            with self.assertRaises(RuntimeError): s.capture_pose([1])
            s.close()
        with self.assertRaises(ValueError): capture_pose(self.profile, [1, 7], {1: {'p': 1500, 'at': 1}}, True)

    def test_keyframes_hold_long_duration_and_safe_transition(self):
        self.project.add_pose(self.pose(600), hold_s=12)
        self.project.add_pose(self.pose(2400), transition_s=.1, hold_s=3)
        r = compile_project(self.project.data, self.profile)
        validate_recording(r, self.profile)
        playback_plan(r, self.profile, [1, 7], 1)
        self.assertTrue(r['segments_summary'][1]['extended'])
        self.assertEqual(r['samples'][-1]['positions'], {'1': 2400, '7': 2400})
        self.assertTrue(all('axis_t' not in row for row in r['samples']))
        self.assertGreater(r['samples'][-1]['t'], 23)
        self.assertTrue(all(20 <= row[2] <= 9999 for row in playback_plan(r, self.profile, [1], .1)))

    def test_trim_interpolates_boundaries_and_preserves_source(self):
        original = take(self.profile); before = copy.deepcopy(original)
        self.project.add_recording(original)
        self.project.update(0, start_s=.25, end_s=1.25)
        r = compile_project(self.project.data, self.profile)
        self.assertEqual(r['samples'][0]['positions']['1'], 1512)
        self.assertEqual(r['samples'][-1]['positions']['1'], 1562)
        self.assertAlmostEqual(r['samples'][-1]['t'], 1)
        self.assertEqual(original, before)
        self.assertEqual(next(iter(self.project.data['sources'].values())), before)

    def test_split_is_continuous_without_new_pause(self):
        self.project.add_recording(take(self.profile)); self.project.split(0, 1)
        r = compile_project(self.project.data, self.profile)
        self.assertAlmostEqual(r['samples'][-1]['t'], 2)
        self.assertEqual(r['segments_summary'][1]['transition_s'], 0)
        playback_plan(r, self.profile, [1], 1)

    def test_remove_middle_adds_bounded_bridge(self):
        self.project.add_recording(take(self.profile)); self.project.remove_range(0, .5, 1.5)
        self.assertEqual([(s['start_s'], s['end_s']) for s in self.project.data['segments']], [(0, .5), (1.5, 2)])
        r = compile_project(self.project.data, self.profile)
        self.assertTrue(any(s['kind'] == 'transition' for s in r['samples']))
        playback_plan(r, self.profile, [1, 7], 1)

    def test_copy_reorder_delete_undo_redo(self):
        self.project.add_pose(self.pose(1500), name='A'); self.project.add_pose(self.pose(1600), name='B')
        self.project.duplicate(0); self.project.move(1, 2); self.project.delete(0)
        self.assertEqual([s['name'] for s in self.project.data['segments']], ['B', 'A 副本'])
        self.project.undo(); self.assertEqual(len(self.project.data['segments']), 3)
        self.project.redo(); self.assertEqual(len(self.project.data['segments']), 2)
        self.project.undo(); self.project.update(0, name='new')
        self.assertEqual(self.project.redo_stack, [])

    def test_local_speed_only_retimes_selected_clip(self):
        self.project.add_recording(take(self.profile), name='A'); self.project.split(0, 1)
        self.project.update(1, speed=.5)
        r = compile_project(self.project.data, self.profile)
        self.assertAlmostEqual(r['samples'][-1]['t'], 3)
        self.assertAlmostEqual(r['segments_summary'][0]['end_s'], 1)

    def test_overspeed_clip_is_not_silently_accepted(self):
        r = take(self.profile)
        for i, row in enumerate(r['samples']): row['positions'] = {'1': 1500+20*i, '7': 1500+20*i}
        self.project.add_recording(r); self.project.update(0, speed=2)
        with self.assertRaises(ValueError): compile_project(self.project.data, self.profile)
        self.project.update(0, speed=.5); playback_plan(compile_project(self.project.data, self.profile), self.profile, [1], 1)

    def test_simulation_taint_survives_import_and_copy(self):
        self.project.add_pose(self.pose(1500, False)); self.project.add_pose(self.pose(1510, True))
        r = compile_project(self.project.data, self.profile)
        with self.assertRaises(ValueError): validate_recording(r, self.profile, live=True)
        p = EditProject(self.profile, [1]); p.add_recording(r); p.duplicate(0)
        with self.assertRaises(ValueError): validate_recording(compile_project(p.data, self.profile), self.profile, live=True)
        self.project.delete(1)
        validate_recording(compile_project(self.project.data, self.profile), self.profile, live=True)

    def test_real_edited_record_reconstructs_and_rejects_tampering(self):
        self.project.add_recording(take(self.profile, False))
        r = compile_project(self.project.data, self.profile)
        validate_recording(r, self.profile, live=True)
        for change in ('target', 'source', 'evidence'):
            bad = copy.deepcopy(r)
            if change == 'target': bad['samples'][1]['positions']['1'] += 1
            elif change == 'source': bad['source'] = 'simulation'
            else: next(iter(bad['edit_project']['sources'].values()))['samples'][1]['positions']['1'] += 1
            with self.subTest(change=change), self.assertRaises(ValueError): validate_recording(bad, self.profile)

    def test_bad_edit_is_atomic_and_missing_axes_not_filled(self):
        self.project.add_recording(take(self.profile)); before = copy.deepcopy(self.project.data)
        for props in ({'start_s': 3}, {'speed': float('nan')}, {'end_s': .001}, {'positions': {'1': 1500}}):
            with self.assertRaises(ValueError): self.project.update(0, **props)
            self.assertEqual(before, self.project.data)
        with self.assertRaises(ValueError): self.project.add_recording(take(self.profile, numbers=[1]))
        self.assertEqual(before, self.project.data)

    def test_import_subset_cannot_reactivate_hidden_source_axes(self):
        single = EditProject(self.profile,[1]); single.add_recording(take(self.profile))
        compiled = compile_project(single.data,self.profile)
        with self.assertRaises(ValueError): self.project.add_recording(compiled)
        self.assertEqual(self.project.data['segments'],[])

    def test_rerecord_pose_preserves_old_capture_for_undo(self):
        self.project.add_pose(self.pose(1500)); old = self.project.data['segments'][0]['source_id']
        self.project.replace_pose(0,self.pose(1600))
        self.assertEqual(compile_project(self.project.data,self.profile)['samples'][0]['positions']['1'],1600)
        self.project.undo()
        self.assertEqual(self.project.data['segments'][0]['source_id'],old)
        self.assertEqual(compile_project(self.project.data,self.profile)['samples'][0]['positions']['1'],1500)

    def test_capture_validation_error_does_not_release_other_axes(self):
        from shadow_play.bus_servo.gui import Worker
        class Session:
            def __init__(self): self.stops=0; self.recording=False; self.closed=False
            def capture_pose(self,numbers): raise PoseCaptureError('outside limits')
            def tick(self,numbers): return None,False
            def stop(self,**kwargs): self.stops+=1
            def close(self): self.closed=True
        commands,events=queue.Queue(),queue.Queue(); worker=Worker(commands,events,threading.Event())
        session=Session(); worker.session=session
        commands.put(('capture_pose',[1])); worker.start()
        seen=[]; deadline=time.monotonic()+2
        try:
            while time.monotonic()<deadline:
                kind,_=events.get(timeout=1); seen.append(kind)
                if kind=='command_done': break
        finally:
            commands.put(('shutdown',None)); worker.join(2)
        self.assertIn('capture_error',seen); self.assertEqual(session.stops,0)
        self.assertTrue(session.closed); self.assertFalse(worker.is_alive())

    def test_stop_does_not_replace_edited_motion_with_previous_raw_take(self):
        from shadow_play.bus_servo.gui import Worker
        class Session:
            recording=False
            record={'old':'raw take'}
            def stop(self,**kwargs): return 'stopped'
            def tick(self,numbers): return None,False
            def close(self): pass
        commands,events=queue.Queue(),queue.Queue(); flag=threading.Event(); flag.set()
        worker=Worker(commands,events,flag); worker.session=Session(); worker.start()
        seen=[]
        try:
            while True:
                kind,_=events.get(timeout=2); seen.append(kind)
                if kind=='idle': break
        finally:
            commands.put(('shutdown',None)); worker.join(2)
        self.assertIn('stopped',seen); self.assertNotIn('record',seen)
        self.assertFalse(worker.is_alive())

    def test_edited_trajectory_runs_through_existing_playback(self):
        p=EditProject(self.profile,[1]); p.add_pose(capture_pose(self.profile,[1],{1:{'p':1500,'at':1}},True),hold_s=.1)
        p.add_pose(capture_pose(self.profile,[1],{1:{'p':1505,'at':2}},True),transition_s=.2,hold_s=.1)
        with tempfile.TemporaryDirectory() as tmp:
            d=SimulationDevice(self.profile); s=TeachingSession(self.profile,d,tmp)
            s.start_playback(compile_project(p.data,self.profile),[1],1)
            deadline=time.monotonic()+2
            while s.playing and time.monotonic()<deadline: s.tick([1]); time.sleep(.005)
            self.assertFalse(s.playing); self.assertEqual(d.positions[1],1505)
            self.assertEqual(d.positions[7],1500); s.close()

    def test_incomplete_take_cannot_be_promoted_to_editable_motion(self):
        r = take(self.profile); r['complete'] = False
        with self.assertRaises(ValueError): self.project.add_recording(r)

    def test_save_reload_project_and_motion_no_overwrite(self):
        self.project.add_pose(self.pose(1500)); self.project.add_recording(take(self.profile))
        with tempfile.TemporaryDirectory() as tmp:
            project_file = Path(tmp)/'part1.project.json'; save_recording(project_file, self.project.data)
            p = EditProject(self.profile, data=json.loads(project_file.read_text(encoding='utf-8')))
            r = compile_project(p.data, self.profile); target = Path(tmp)/'part1.motion.json'; save_recording(target, r)
            validate_recording(json.loads(target.read_text(encoding='utf-8')), self.profile)
            with self.assertRaises(FileExistsError): save_recording(project_file, self.project.data)


if __name__ == '__main__': unittest.main()
