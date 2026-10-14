import copy,hashlib,json,unittest
from unittest.mock import patch
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
    def test_tree_position_moves_only_yaw_and_reviews_each_segment(self):
        f,p,args=self.setup_device();p.update(profile=t.PARK,expected_pulses_us=t.BASE[:6]+[1540,1500,1540,1500])
        for i,v in enumerate(p['expected_pulses_us']):f.r.values[0x80+4*i]=v
        with patch.object(t,'validate'):
            d=t.TigerLeapSession(f.r,p,f.host,**args)
        events=[]
        def emit(r):
            events.append(r)
            if r['event'] in ('reference_held','launch_position_held'):f.host.action=('demo',r['state']['sequence'])
        t.run(d,emit,f.sleep)
        self.assertEqual(sum(r['event']=='launch_position_held' for r in events),3)
        prior=p['expected_pulses_us']
        for r in events:
            if r['event']!='probe_step':continue
            q=r['state']['pulse_us'];self.assertEqual(q[:6],t.BASE[:6]);self.assertEqual((q[7],q[9]),(1500,1500))
            self.assertGreaterEqual(q[6],prior[6]);self.assertEqual(q[6],q[8])
            self.assertLessEqual(q[6]-prior[6],3);prior=q
        self.assertTrue(t.closed_tiger_reference(events));self.assertEqual(prior[6],1840)
    def test_head_lower_keeps_other_nine_commands_fixed(self):
        f,p,args=self.setup_device();p.update(profile=t.PRESS,expected_pulses_us=t.BASE[:6]+[1840,1500,1840,1500])
        for i,v in enumerate(p['expected_pulses_us']):f.r.values[0x80+4*i]=v
        with patch.object(t,'validate'):d=t.TigerLeapSession(f.r,p,f.host,**args)
        events=[]
        def emit(r):
            events.append(r)
            if r['event'] in ('reference_held','launch_position_held'):f.host.action=('demo',r['state']['sequence'])
        t.run(d,emit,f.sleep)
        prior=p['expected_pulses_us']
        for r in events:
            if r['event']!='probe_step':continue
            q=r['state']['pulse_us']
            self.assertEqual(q[:7]+q[8:],prior[:7]+prior[8:])
            self.assertTrue(0<=prior[7]-q[7]<=2);prior=q
        self.assertTrue(t.closed_tiger_reference(events))
        self.assertEqual(prior[7],1460)
        self.assertEqual(events[-1]['state']['enabled_mask'],0)

    def test_ten_degree_lower_and_small_left_keeps_rear_pitch_fixed(self):
        f,p,args=self.setup_device();p.update(profile=t.LOWER_LEFT,expected_pulses_us=t.BASE[:6]+[1840,1423,1840,1500])
        for i,v in enumerate(p['expected_pulses_us']):f.r.values[0x80+4*i]=v
        with patch.object(t,'validate'):d=t.TigerLeapSession(f.r,p,f.host,**args)
        events=[]
        def emit(r):
            events.append(r)
            if r['event']=='reference_held':f.host.action=('demo',r['state']['sequence'])
        t.run(d,emit,f.sleep);prior=p['expected_pulses_us']
        for r in events:
            if r['event']!='probe_step':continue
            q=r['state']['pulse_us'];self.assertEqual(q[:6],t.BASE[:6]);self.assertEqual(q[9],1500)
            self.assertEqual(q[6],q[8]);self.assertTrue(all(0<=prior[i]-q[i]<=2 for i in (6,7,8)));prior=q
        self.assertEqual(prior[6:],[1810,1349,1810,1500]);self.assertTrue(t.closed_tiger_reference(events))

    def test_screen_approach_pauses_before_second_step(self):
        f,p,args=self.setup_device();p.update(profile=t.SCREEN,expected_pulses_us=t.BASE[:6]+[1810,1349,1810,1500])
        for i,v in enumerate(p['expected_pulses_us']):f.r.values[0x80+4*i]=v
        with patch.object(t,'validate'):d=t.TigerLeapSession(f.r,p,f.host,**args)
        events=[]
        def emit(r):
            events.append(r)
            if r['event'] in ('reference_held','launch_position_held'):f.host.action=('demo',r['state']['sequence'])
        t.run(d,emit,f.sleep)
        self.assertEqual(sum(e['event']=='launch_position_held' for e in events),1)
        self.assertEqual(events[-1]['state']['pulse_us'],t.BASE[:6]+[1730,1275,1730,1500])
        self.assertTrue(t.closed_tiger_reference(events))

    def test_screen_leap_staggers_rods_and_returns_to_new_reference(self):
        f,p,args=self.setup_device();p.update(profile=t.SCREEN_LEAP,expected_pulses_us=t.BASE[:6]+[1730,1275,1730,1500])
        for i,v in enumerate(p['expected_pulses_us']):f.r.values[0x80+4*i]=v
        with patch.object(t,'validate'):d=t.TigerLeapSession(f.r,p,f.host,**args)
        events=[]
        def emit(r):
            events.append(r)
            if r['event']=='reference_held':f.host.action=('demo',r['state']['sequence'])
        t.run(d,emit,f.sleep)
        self.assertTrue(t.closed_tiger_reference(events))
        self.assertEqual(events[-1]['state']['pulse_us'],p['expected_pulses_us'])
        ends=[e['state']['pulse_us'][6:] for e in events if e['event']=='probe_complete']
        self.assertEqual(ends[0][3],ends[1][3]);self.assertGreater(ends[1][1],ends[0][1])
        self.assertLess(ends[2][3],ends[1][3]);self.assertLess(ends[3][1],ends[2][1])
        self.assertEqual(ends[3][3],ends[2][3])
        self.assertTrue(all(e['state']['pulse_us'][:6]==t.BASE[:6] for e in events if 'state' in e))

    def test_up_left_leap_crouches_rear_then_lifts_head_first(self):
        f,p,args=self.setup_device();p.update(profile=t.UPLEFT,expected_pulses_us=t.BASE[:6]+[1730,1275,1730,1500])
        for i,v in enumerate(p['expected_pulses_us']):f.r.values[0x80+4*i]=v
        with patch.object(t,'validate'):d=t.TigerLeapSession(f.r,p,f.host,**args)
        events=[]
        def emit(r):
            events.append(r)
            if r['event']=='reference_held':f.host.action=('demo',r['state']['sequence'])
        t.run(d,emit,f.sleep);self.assertTrue(t.closed_tiger_reference(events))
        self.assertEqual(events[-1]['state']['pulse_us'],p['expected_pulses_us'])
        ends=[e['state']['pulse_us'][6:] for e in events if e['event']=='probe_complete']
        self.assertEqual(ends[0],[1720,1275,1720,1560])
        self.assertEqual(ends[1][3],1560);self.assertEqual(ends[1][1]-ends[0][1],150)
        self.assertLess(ends[2][3],ends[1][3]);self.assertGreater(ends[2][1],ends[1][1])
        self.assertEqual(ends[3][3],ends[2][3]);self.assertLess(ends[3][1],ends[2][1])
        self.assertTrue(all(e['state']['pulse_us'][:6]==t.BASE[:6] for e in events if 'state' in e))

    def test_staggered_right_start_waits_then_lifts_head_before_rear(self):
        f,p,args=self.setup_device();prior=[]
        def first(r):
            prior.append(r)
            if r['event']=='reference_held':f.host.action=('demo',r['state']['sequence'])
        t.run(t.TigerLeapSession(f.r,p,f.host,**args),first,f.sleep)
        self.assertTrue(t.closed_tiger_reference(prior))
        raw='\n'.join(json.dumps(r) for r in prior).encode();old_read=args['read']
        args['read']=lambda path:raw if path==p['baseline_source']['path'] else old_read(path)
        p.update(profile=t.STAGGERED,expected_sequence=prior[-1]['state']['sequence'])
        p['baseline_source']['sha256']=hashlib.sha256(raw).hexdigest()
        events=[]
        def emit(r):
            events.append(r)
            if r['event'] in ('reference_held','launch_position_held'):f.host.action=('demo',r['state']['sequence'])
        t.run(t.TigerLeapSession(f.r,p,f.host,**args),emit,f.sleep)
        self.assertTrue(t.closed_tiger_reference(events))
        ends=[r['state']['pulse_us'][6:] for r in events if r['event']=='probe_complete']
        self.assertEqual(ends[0],[1540,1500,1540,1500])
        self.assertEqual(ends[2][3],ends[1][3])
        self.assertEqual(ends[3][1],ends[2][1])
        self.assertLess(ends[4][1],ends[3][1]);self.assertEqual(ends[4][3],ends[3][3])
        self.assertTrue(all(r['state']['pulse_us'][:6]==t.BASE[:6] for r in events if 'state' in r))
        self.assertEqual(events[-1]['state']['enabled_mask'],0)
        bad=copy.deepcopy(events);next(r for r in bad if r['event']=='probe_step')['state']['pulse_us'][0]+=1
        with self.assertRaises(ValueError):t.closed_tiger_reference(bad)
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
