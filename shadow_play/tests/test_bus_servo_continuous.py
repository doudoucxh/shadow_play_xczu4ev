"""Board cadence, real RPC overhead, explicit successor chains and failures."""
import copy
from pathlib import Path
import unittest
from unittest.mock import Mock

from shadow_play.bus_servo.model import Profile, new_recording, playback_plan, validate_recording
from shadow_play.bus_servo.service import Controller
from shadow_play.bus_servo.session import TeachingSession, PlaybackRejected
from shadow_play.bus_servo.transport import RemoteDevice
from shadow_play.bus_servo.editing import EditProject, compile_project

PROFILE = Path(__file__).resolve().parents[1]/'config/bus_servo.json'


class Clock:
    def __init__(self): self.now = 10.
    def __call__(self): return self.now
    def advance(self, seconds): self.now += seconds


class Board:
    simulation = False
    def __init__(self, profile, clock):
        self.profile,self.clock = profile,clock
        self.positions = {n:1500 for n in profile.axes}
        self.moves,self.motions = [],{}
        self.failed = self.claimed = False
        self.fail_read = False
        self.last_kick = clock()
        self.reads = self.stops = 0
    def kick(self):
        if self.claimed and self.clock()-self.last_kick > 1:
            raise TimeoutError('test FPGA lease expired')
        self.last_kick = self.clock()
    def sample(self):
        for n,(p,q,t,seconds) in self.motions.items():
            f = min(1,max(0,(self.clock()-t)/seconds))
            self.positions[n] = round(p+(q-p)*f)
    def read(self, numbers):
        self.kick(); self.reads += 1; self.clock.advance(.045)
        if self.fail_read: raise TimeoutError('feedback lost')
        self.sample()
        return {n:dict(p=self.positions[n],at=self.clock()) for n in numbers}
    def move(self, targets, ms):
        self.kick(); self.sample(); self.claimed = True
        self.moves.append((self.clock(),dict(targets),ms))
        for n,p in targets.items():
            n = int(n); self.motions[n] = self.positions[n],p,self.clock(),ms/1000
        self.clock.advance(.010)  # UART group transmission
    def board_status(self): return dict(faults=0,lease=int(self.claimed))
    def stop(self): self.stops += 1; self.claimed = False; self.motions.clear()
    def close(self): pass


class Link:
    simulation = False
    continuous_playback = adaptive_playback = True
    playback_speed_limit_enabled = False
    def __init__(self, profile, clock):
        self.clock = clock; self.board = Board(profile,clock)
        self.controller = Controller(profile,self.board,True,True,clock,clock.advance)
        self.controller.verified = set(profile.axes)
        self.calls = []; self.chain = 0
    def request(self, op, payload):
        self.calls.append(op); self.clock.advance(.017)
        result = self.controller.execute(dict(seq=self.controller.last_sequence+1,op=op,payload=payload))
        self.clock.advance(.035)
        return result
    def connect(self): return {}
    def read(self, numbers): return self.request('read',dict(numbers=numbers))
    def board_status(self): return self.request('status',{})
    def playback_step(self,targets,ms,first=False):
        result = self.request('play_step',dict(targets=targets,duration_ms=ms,
                              previous=0 if first else self.chain,attended=True))
        self.chain = result['chain']
        result['positions'] = {n:dict(p=p,at=at) for n,p,at in result['feedback']}
        return result
    def stop(self): return self.request('stop',{})
    def close(self): pass


def take(profile, frames=20, interval=.14):
    record = new_recording(profile,list(profile.axes),False,20)
    for i in range(frames):
        values = {str(n):1500 for n in profile.axes}
        values['7'] = 1500+(i%6)*45 if i%12<6 else 1500+(11-i%12)*45
        record['samples'].append(dict(t=i*interval,positions=values,
                                     axis_t={str(n):i*interval for n in profile.axes}))
    record['complete'] = True
    return record


class ContinuousTests(unittest.TestCase):
    def setUp(self):
        self.profile = Profile.load(PROFILE)
        self.profile.data['playback_speed_limit_enabled'] = False
        self.clock = Clock(); self.link = Link(self.profile,self.clock)
        self.session = TeachingSession(self.profile,self.link,'.',clock=self.clock)
        self.session.ready_axes = set(self.profile.axes)

    def test_recorded_speed_has_no_30_degree_cap_and_source_is_preserved(self):
        record = take(self.profile); original = copy.deepcopy(record)
        plan = playback_plan(record,self.profile,list(self.profile.axes),1)
        self.assertEqual(plan.retimed_intervals,0)
        self.assertAlmostEqual(plan.playback_times[-1],round(record['samples'][-1]['t']*1000)/1000)
        self.assertGreater(45*.135/.14,30)
        self.assertEqual(record,original)
        self.assertAlmostEqual(playback_plan(record,self.profile,[7],.5).playback_times[-1],5.32)

    def test_continuous_rpc_overhead_is_overlapped_not_added_to_every_segment(self):
        s = self.session; s.start_playback(take(self.profile,107),list(self.profile.axes),1)
        progress = []
        for _ in range(4000):
            s.tick(list(self.profile.axes)); progress.append(s.playback_elapsed())
            if not s.playing: break
            self.clock.advance(.01)
        self.assertFalse(s.playing)
        self.assertEqual(len(self.link.board.moves),106)
        self.assertEqual([m[1] for m in self.link.board.moves],[x[1] for x in s.plan])
        self.assertLess(self.clock()-s.play_start-s.play_end,.35)
        for previous,current in zip(self.link.board.moves,self.link.board.moves[1:]):
            self.assertAlmostEqual(current[0]-previous[0],previous[2]/1000,places=6)
        self.assertEqual(progress,sorted(progress))
        self.assertEqual(self.link.board.reads,108)  # start, per-segment, final
        self.assertNotIn('status',self.link.calls)

    def test_stop_discards_continuation_and_does_not_send_next_target(self):
        s = self.session; s.start_playback(take(self.profile),[7])
        s.tick([7]); count = len(self.link.board.moves)
        s.cancel_requested = lambda:True
        self.clock.advance(.15); s.tick([7])
        self.assertEqual(len(self.link.board.moves),count)
        s.stop(); self.assertFalse(s.playing); self.assertEqual(self.link.board.stops,1)
        with self.assertRaisesRegex(ValueError,'chain'):
            self.link.playback_step({'7':1600},140)
        self.assertEqual(len(self.link.board.moves),count)

    def test_feedback_failure_prevents_successor(self):
        s = self.session; s.start_playback(take(self.profile),[7]); s.tick([7])
        self.link.board.fail_read = True
        self.clock.now = s.play_due-.21
        with self.assertRaisesRegex(TimeoutError,'feedback lost'): s.tick([7])
        self.assertEqual(len(self.link.board.moves),1)

    def test_no_first_target_on_bad_range_attendance_chain_or_early_request(self):
        for payload in (
            dict(targets={'7':2500},duration_ms=140,previous=0,attended=True),
            dict(targets={'7':1500},duration_ms=140,previous=0,attended=False),
            dict(targets={'7':1500},duration_ms=140,previous=1,attended=True),
            dict(targets={'7':1500},duration_ms=19,previous=0,attended=True)):
            with self.assertRaises(ValueError): self.link.request('play_step',payload)
        self.assertFalse(self.link.board.moves)
        self.link.playback_step({'7':1500},2000,first=True)
        with self.assertRaisesRegex(ValueError,'early'): self.link.playback_step({'7':1510},140)
        self.assertEqual(len(self.link.board.moves),1)

    def test_long_segments_keep_lease_and_thread_stalls_abort(self):
        s=self.session; s.start_playback(take(self.profile,3,.5),[7],.1)
        for _ in range(1500):
            s.tick([7])
            if not s.playing: break
            self.clock.advance(.01)
        self.assertFalse(s.playing)
        self.assertEqual(len(self.link.board.moves),2)
        s.start_playback(take(self.profile),[1]); s.tick([1])
        count=len(self.link.board.moves);self.clock.advance(1.01)
        with self.assertRaisesRegex(TimeoutError,'超过1秒'):s.tick([1])
        self.assertEqual(len(self.link.board.moves),count)

    def test_missing_board_capability_rejected_without_queries_or_motion(self):
        self.link.continuous_playback=False
        with self.assertRaises(PlaybackRejected): self.session.start_playback(take(self.profile),[7])
        self.assertFalse(self.link.calls)

    def test_new_edit_projects_accept_fast_material_old_compiles_keep_policy(self):
        record=take(self.profile)
        project=EditProject(self.profile,[7]);project.add_recording(record)
        compiled=compile_project(project.data,self.profile)
        validate_recording(compiled,self.profile,live=True)
        self.assertFalse(project.data['playback_speed_limit_enabled'])
        old=copy.deepcopy(project.data);old.pop('playback_speed_limit_enabled')
        with self.assertRaisesRegex(ValueError,'速度'):compile_project(old,self.profile)

    def test_transport_validates_reply_and_does_not_retry(self):
        d=RemoteDevice.__new__(RemoteDevice);d.continuous_playback=True;d.playback_speed_limit_enabled=False
        d.sequence=4;d.playback_chain=3
        reply=dict(sent=True,chain=4,duration_ms=140,requested_duration_ms=140,dispatch_age_s=.01,feedback=[[7,1500,10.]])
        d.request=Mock(return_value=reply)
        self.assertEqual(d.playback_step({'7':1600},140)['positions'][7]['p'],1500)
        self.assertEqual(d.request.call_args.args[1]['previous'],3)
        d.request.reset_mock();d.request.return_value=dict(reply,duration_ms=139)
        with self.assertRaises(RuntimeError):d.playback_step({'7':1600},140)
        d.request.assert_called_once()


if __name__=='__main__':unittest.main()
