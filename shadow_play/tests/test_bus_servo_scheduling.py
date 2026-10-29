"""Replay over delayed RPCs: preserve ordering, full durations and stop behavior."""
from pathlib import Path
import unittest
from unittest.mock import patch

from shadow_play.bus_servo.device import SimulationDevice
from shadow_play.bus_servo.model import Profile
from shadow_play.bus_servo.session import TeachingSession
from shadow_play.bus_servo.timeline import PlaybackTimeline
from shadow_play.tests.test_bus_servo import recording

PROFILE=Path(__file__).resolve().parents[1]/'config/bus_servo.json'


class DelayedDevice:
    simulation=False
    def __init__(self,profile,clock):
        self.inner=SimulationDevice(profile);self.clock=clock
        self.calls=[];self.moves=[];self.fail_read=False;self.on_read=lambda:None
    def connect(self):return {}
    def read(self,numbers):
        self.calls.append('read');self.clock[0]+=.13+(len(self.calls)%3)*.025
        if self.fail_read:raise TimeoutError('feedback timeout')
        self.on_read()
        return self.inner.read(numbers)
    def board_status(self):
        self.calls.append('status');self.clock[0]+=.03
        return {'faults':0}
    def move(self,targets,ms):
        self.calls.append('move');start=self.clock[0]
        self.clock[0]+=.15 # board validates feedback before dispatch
        self.inner.move(targets,ms)
        self.clock[0]+=.025 # transmission/acknowledgement after last dispatch
        self.moves.append((start,self.clock[0],dict(targets),ms))
    def stop(self):return self.inner.stop()
    def close(self):self.inner.close()


class SchedulingTests(unittest.TestCase):
    def setUp(self):
        self.profile=Profile.load(PROFILE);self.now=[10.0]
        self.time_patch=patch('shadow_play.bus_servo.device.time.monotonic',side_effect=lambda:self.now[0])
        self.time_patch.start()
        self.device=DelayedDevice(self.profile,self.now)
        self.session=TeachingSession(self.profile,self.device,'.',clock=lambda:self.now[0])
        self.session.ready_axes=set(self.profile.axes)
        self.record=recording(self.profile,simulation=False)
        self.session.start_playback(self.record,[1,7],.5)
    def tearDown(self):self.session.close();self.time_patch.stop()

    def test_variable_latency_completes_without_burst_skips_or_shortened_moves(self):
        s=self.session;progress=[];ticks=0
        while s.playing and ticks<2000:
            before=len(self.device.calls)
            s.tick([1,7]);progress.append(s.playback_elapsed())
            self.assertLessEqual(len(self.device.calls)-before,1)
            self.now[0]+=.01;ticks+=1
        self.assertFalse(s.playing)
        self.assertEqual(len(self.device.moves),len(s.plan))
        self.assertEqual([m[2] for m in self.device.moves],[step[1] for step in s.plan])
        for previous,current in zip(self.device.moves,self.device.moves[1:]):
            self.assertGreaterEqual(current[0]+1e-9,previous[1]+previous[3]/1000)
        self.assertEqual(progress,sorted(progress))
        self.assertAlmostEqual(progress[-1],s.play_end)
        self.assertGreater(self.now[0]-s.play_start,s.play_end)
        self.assertEqual(self.device.inner.positions[2],1500)
        self.assertIn('status',self.device.calls)

    def test_final_feedback_waits_full_duration_after_acknowledgement(self):
        s=self.session
        while s.index<len(s.plan):s.tick([1,7]);self.now[0]+=.01
        ack=self.device.moves[-1][1];end=ack+self.device.moves[-1][3]/1000
        s.next_poll=s.next_board_poll=end+1
        self.now[0]=end-.001
        self.assertFalse(s.tick([1,7])[1]);self.assertTrue(s.playing)
        self.now[0]=end
        self.assertTrue(s.tick([1,7])[1]);self.assertFalse(s.playing)

    def test_large_thread_stall_is_not_automatically_resumed(self):
        self.session.tick([1,7]);count=len(self.device.moves)
        self.now[0]+=1.01
        with self.assertRaisesRegex(TimeoutError,'超过1秒'):self.session.tick([1,7])
        self.assertEqual(len(self.device.moves),count)

    def test_stop_requested_during_feedback_prevents_next_target(self):
        s=self.session;s.tick([1,7]);cancel=[False]
        s.cancel_requested=lambda:cancel[0]
        self.device.on_read=lambda:cancel.__setitem__(0,True)
        self.now[0]+=.01;s.tick([1,7])
        self.assertTrue(cancel[0]);count=len(self.device.moves)
        self.now[0]=s.play_due+.2;s.tick([1,7])
        self.assertEqual(len(self.device.moves),count)

    def test_real_feedback_failure_still_raises_without_next_motion(self):
        self.session.tick([1,7]);count=len(self.device.moves)
        self.device.fail_read=True;self.now[0]+=.01
        with self.assertRaisesRegex(TimeoutError,'feedback timeout'):self.session.tick([1,7])
        self.assertEqual(len(self.device.moves),count)

    def test_single_excessively_long_rpc_still_aborts(self):
        self.session.tick([1,7]);count=len(self.device.moves)
        self.device.on_read=lambda:self.now.__setitem__(0,self.now[0]+1.1)
        self.now[0]+=.01
        with self.assertRaisesRegex(TimeoutError,'通信停顿超过1秒'):self.session.tick([1,7])
        self.assertEqual(len(self.device.moves),count)

    def test_progress_holds_at_last_sent_interval_and_displays_wall_time(self):
        s=self.session;s.tick([1,7])
        self.now[0]=s.play_due+.1
        self.assertAlmostEqual(s.playback_elapsed(),.2)
        timeline=PlaybackTimeline(self.record,.5,plan=s.plan)
        p=timeline.snapshot(s.playback_elapsed(),'playing',wall_elapsed=self.now[0]-s.play_start)
        self.assertAlmostEqual(p['source_s'],.1)
        self.assertGreater(p['duration_s'],s.play_end)
        self.assertGreater(p['communication_delay_s'],0)
        self.assertEqual(p['fraction'],.25)
        self.assertEqual(p['state'],'playing')


if __name__=='__main__':unittest.main()
