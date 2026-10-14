import copy,json,unittest
from pathlib import Path
import test_hand_crossing_session as fixture
import tiger_leap_session as t
class TigerLeapTests(unittest.TestCase):
    def setup_device(self):
        f=fixture.CrossingTests();f.setUp();self.addCleanup(f.doCleanups)
        f.prepare_fast(fixture.h.TIGER_DIRECTED_PROFILE)
        p=copy.deepcopy(f.p);p.update(profile=t.PROFILE,tiger_hardware_unchanged=True,static_reference_review_required=True,
            historical_tiger_reference={'path':'/tmp/tiger_duet_reference_20261012.json','sha256':t.HISTORICAL_SHA})
        historical=(Path(__file__).resolve().parents[1]/'config/person_tiger_duet_result.20261012.json').read_bytes()
        read=lambda path:historical if path==p['historical_tiger_reference']['path'] else f.raw
        args=dict(motion_inhibit_paths=[f.lock],cancel_path=f.lock.with_name('cancel'),clock=lambda:f.now,wall=lambda:1000,read=read,boot_id_path=f.boot,image_marker=f.marker)
        return f,p,args
    def test_only_tiger_moves_and_reference_review_precedes_route(self):
        f,p,args=self.setup_device();d=t.TigerLeapSession(f.r,p,f.host,**args);events=[]
        def emit(r):
            events.append(dict(r,time=f.now))
            if r['event']=='reference_held':
                self.assertEqual(d.cursor,0);f.host.action=('demo',r['state']['sequence'])
        t.run(d,emit,f.sleep);prior=t.BASE;last=-1
        for r in events:
            if r['event']!='probe_step':continue
            q=r['state']['pulse_us'];self.assertEqual(q[:6],t.BASE[:6]);self.assertEqual(r['state']['enabled_mask'],960)
            self.assertTrue(all(1440<=v<=1560 for v in q[6:]));self.assertLessEqual(max(abs(a-b) for a,b in zip(q,prior)),t.STEPS[r['axis']])
            self.assertGreaterEqual(r['time']-last,.02-1e-9);prior=q;last=r['time']
        self.assertEqual(events[-1]['state']['enabled_mask'],0);self.assertEqual(events[-1]['state']['pulse_us'],t.BASE)
        self.assertEqual(f.lock.read_text(),'incident')
    def test_changed_linkage_rejected_before_writes(self):
        f,p,args=self.setup_device();p['tiger_hardware_unchanged']=False
        with self.assertRaises(ValueError):t.TigerLeapSession(f.r,p,f.host,**args)
        self.assertEqual(f.r.writes,[])
    def test_no_start_without_static_review_and_cancel_turns_off(self):
        f,p,args=self.setup_device();d=t.TigerLeapSession(f.r,p,f.host,**args);events=[]
        def emit(r):
            events.append(r)
            if r['event']=='reference_held':Path(args['cancel_path']).touch()
        with self.assertRaises(RuntimeError):t.run(d,emit,f.sleep)
        self.assertFalse(any(r['event']=='probe_started' for r in events));self.assertEqual(events[-1]['state']['enabled_mask'],0)
    def test_fault_during_leap_stops_without_return_or_retry(self):
        f,p,args=self.setup_device();d=t.TigerLeapSession(f.r,p,f.host,**args);events=[]
        def emit(r):
            events.append(r)
            if r['event']=='reference_held':f.host.action=('demo',r['state']['sequence'])
            if r['event']=='probe_step' and r['axis']==2:raise RuntimeError('injected camera loss')
        with self.assertRaisesRegex(RuntimeError,'injected camera loss'):t.run(d,emit,f.sleep)
        self.assertFalse(events[-1]['normal_frame_stop']);self.assertEqual(events[-1]['state']['enabled_mask'],0)
if __name__=='__main__':unittest.main()
