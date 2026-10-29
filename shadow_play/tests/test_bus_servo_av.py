"""Joint cuts, portable assets and audio follow the accepted motion clock."""
import copy
import json
from pathlib import Path
import queue
import shutil
import tempfile
import threading
import unittest
from unittest.mock import Mock,patch
import wave

import numpy as np

from shadow_play.bus_servo.av_editing import AVProject,clip_end,duration,compile_motion,load_file,save_bundle,MotionSampler
from shadow_play.bus_servo.audio import AudioTrack,AudioPlayer,RATE,file_sha,import_audio,export_wav
from shadow_play.bus_servo.device import SimulationDevice
from shadow_play.bus_servo.gui import Worker
from shadow_play.bus_servo.model import Profile,validate_recording,playback_plan
from shadow_play.bus_servo.session import TeachingSession
from shadow_play.tests.test_bus_servo import recording

PROFILE=Path(__file__).resolve().parents[1]/'config/bus_servo.json'


def make_asset(path):
    # Deliberately distinct half-second blocks make edit alignment measurable.
    samples=np.repeat(np.array([1000,2000,3000,4000],dtype='<i2'),RATE//2)
    with wave.open(str(path),'wb') as w:
        w.setnchannels(2);w.setsampwidth(2);w.setframerate(RATE);w.writeframes(np.column_stack((samples,samples)).tobytes())
    return dict(file=str(path),sha256=file_sha(path),name='测试音频',duration_s=2.,sample_rate=RATE,channels=2,peaks=[.1]*100)


class AVTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.profile=Profile.load(PROFILE);self.project=AVProject(self.profile,[1,7])
        self.record=recording(self.profile,simulation=False)
        for r in self.record['samples']:
            r['t']*=5;r['axis_t']={k:t*5 for k,t in r['axis_t'].items()}
        self.project.add_motion(self.record);self.asset=make_asset(self.root/'source.wav')
        self.project.add_audio(self.asset)
    def tearDown(self):self.tmp.cleanup()

    def test_joint_ripple_delete_keeps_source_coordinates_and_alignment(self):
        original=copy.deepcopy(self.project.data)
        self.project.cut_range(.5,1.5)
        for kind in ('audio','motion'):
            clips=sorted((c for c in self.project.data['clips'] if c['kind']==kind),key=lambda c:c['at_s'])
            self.assertEqual([(c['at_s'],c['in_s'],c['out_s']) for c in clips],[(0,0,.5),(.5,1.5,2)])
        track=AudioTrack(self.project.data)
        pcm=np.frombuffer(track.render([.25,.75]),dtype='<i2').reshape(-1,2)
        self.assertEqual(pcm[:,0].tolist(),[1000,4000])
        self.assertEqual(self.project.data['motion_sources'],original['motion_sources'])
        self.project.history();self.assertEqual(self.project.data,original)
        self.project.history(True);self.assertAlmostEqual(duration(self.project.data),1.)

    def test_keep_range_and_split_both_tracks(self):
        self.project.cut_range(.5,1.5,True);self.project.split(.5)
        self.assertEqual(len(self.project.data['clips']),4)
        self.assertAlmostEqual(duration(self.project.data),1)
        self.assertEqual({c['in_s'] for c in self.project.data['clips']},{.5,1.})

    def test_individual_trim_speed_offset_and_silence(self):
        audio=self.project.data['clips'][1]
        self.project.update(audio['id'],at_s=.25,in_s=.5,out_s=1.5,speed=2,gain=.5)
        track=AudioTrack(self.project.data)
        pcm=np.frombuffer(track.render([0,.3,.55,.8]),dtype='<i2').reshape(-1,2)
        self.assertEqual(pcm[:,0].tolist(),[0,1000,1500,0])

    def test_motion_overlap_rejected_transactionally_and_audio_can_mix(self):
        before=copy.deepcopy(self.project.data)
        with self.assertRaisesRegex(ValueError,'重叠'):self.project.add_motion(self.record,at=1)
        self.assertEqual(before,self.project.data)
        self.project.add_audio(self.asset)
        self.assertEqual(np.frombuffer(AudioTrack(self.project.data).render([.1]),dtype='<i2')[0],2000)

    def test_export_verification_and_source_provenance(self):
        self.project.cut_range(.25,1.75,True)
        motion=compile_motion(self.project.data,self.profile);validate_recording(motion,self.profile,live=True)
        motion['samples'][1]['positions']['1']+=1
        with self.assertRaisesRegex(ValueError,'不一致'):validate_recording(motion,self.profile)
        self.project=AVProject(self.profile,[1,7]);self.project.add_motion(recording(self.profile))
        with self.assertRaisesRegex(ValueError,'Simulation'):validate_recording(compile_motion(self.project.data,self.profile),self.profile,live=True)

    def test_sparse_samples_not_upsampled_into_extra_serial_transactions(self):
        motion=compile_motion(self.project.data,self.profile)
        self.assertEqual(len(motion['samples']),len(self.record['samples']))
        self.assertEqual(motion['samples'][-1]['t'],2)

    def test_tail_audio_holds_last_pose_and_fast_splice_respects_speed_plan(self):
        self.project.update(self.project.data['clips'][1]['id'],at_s=1)
        motion=compile_motion(self.project.data,self.profile)
        self.assertEqual(motion['samples'][-1]['positions'],self.record['samples'][-1]['positions'])
        self.assertEqual(motion['samples'][-1]['t'],3.)
        plan=playback_plan(motion,self.profile,[1,7],2)
        before=motion['samples'][0]['positions']
        for _,targets,ms in plan:
            for n in (1,7):
                a=self.profile.axes[n]
                self.assertLessEqual(abs(a.degrees(targets[str(n)])-a.degrees(before[str(n)])),a.max_speed*ms/1000+1e-8)
            before=targets

    def test_portable_project_and_motion_survive_directory_move(self):
        for name,data in [('show.json',self.project.data),('motion.json',compile_motion(self.project.data,self.profile))]:
            save_bundle(self.root/name,data)
            with self.assertRaises(FileExistsError):save_bundle(self.root/name,data)
        moved=self.root/'moved';moved.mkdir()
        for name in ('show.json','show.assets','motion.json','motion.assets'):shutil.move(str(self.root/name),moved/name)
        for name in ('show.json','motion.json'):
            loaded=load_file(moved/name,self.profile);track=AudioTrack(loaded.get('av_project',loaded))
            self.assertEqual(np.frombuffer(track.render([.6]),dtype='<i2')[0],2000)

    def test_changed_or_missing_audio_is_rejected_before_play(self):
        source=self.root/'source.wav';source.unlink()
        with self.assertRaises(FileNotFoundError):AudioTrack(self.project.data)
        make_asset(source)
        with source.open('r+b') as f:f.seek(44);f.write(b'xx')
        with self.assertRaisesRegex(ValueError,'改变'):AudioTrack(self.project.data)

    def test_audio_wave_export_matches_joint_edit_and_does_not_overwrite(self):
        self.project.cut_range(.5,1.5)
        out=self.root/'out.wav';export_wav(out,AudioTrack(self.project.data),1)
        with wave.open(str(out),'rb') as w:
            self.assertEqual(w.getnframes(),RATE);w.setpos(RATE*3//4)
            self.assertEqual(np.frombuffer(w.readframes(1),dtype='<i2')[0],4000)
        with self.assertRaises(FileExistsError):export_wav(out,AudioTrack(self.project.data),1)

    def test_import_decoder_creates_verified_copy_without_changing_source(self):
        original=file_sha(self.root/'source.wav')
        asset=import_audio(self.root/'source.wav',self.root/'media')
        self.assertEqual(original,file_sha(self.root/'source.wav'))
        self.assertAlmostEqual(asset['duration_s'],2);self.assertGreater(len(asset['peaks']),10)

    def test_incomplete_or_missing_axis_recordings_cannot_enter_project(self):
        bad=copy.deepcopy(self.record);bad['complete']=False
        with self.assertRaises(ValueError):self.project.add_motion(bad)
        with self.assertRaises(ValueError):AVProject(self.profile,[1,2,7]).add_motion(self.record)


class AudioClockTests(unittest.TestCase):
    def test_segment_clock_freezes_after_acknowledged_end(self):
        # Exercise the exact mapper used by the audio output thread, no speaker.
        player=AudioPlayer.__new__(AudioPlayer);player.lock=threading.Lock()
        player.segment(2,3,10,2)
        source,active=player.mapper(np.array([9.9,10,11,12,13]))
        self.assertEqual(source.tolist(),[2,2,2.5,3,3])
        self.assertEqual(active.tolist(),[False,True,True,False,False])

    def test_preview_seek_and_rate_map_share_source_clock(self):
        player=AudioPlayer.__new__(AudioPlayer);player.lock=threading.Lock()
        player.preview([0,2,4],[0,1,3],10,1)
        source,active=player.mapper(np.array([10,11,12,14]))
        self.assertEqual(source.tolist(),[.5,1,2,3]);self.assertEqual(active.tolist(),[True,True,True,False])

    def test_worker_only_updates_audio_for_new_accepted_segments(self):
        worker=Worker(queue.Queue(),queue.Queue(),threading.Event());player=Mock(error=None);worker.audio_player=player
        s=Mock(index=0);worker.session=s;worker.sync_audio();player.segment.assert_not_called()
        s.index=1;s.plan=Mock(source_times=[0,.1,.2]);s.segment_started=10;s.segment_duration_ms=450
        worker.sync_audio();worker.sync_audio();player.segment.assert_called_once_with(0,.1,10,.45)
        worker.stop_audio();player.close.assert_called_once_with(wait=False)

    def test_worker_audio_finishes_or_faults_with_motion(self):
        for fail in (False,True):
            now=[0.];events=queue.Queue();players=[];moves=[]
            class Player:
                error=None
                def __init__(self,track):self.segments=[];self.closed=False;players.append(self)
                def segment(self,*args):self.segments.append(args)
                def close(self,wait=True):self.closed=True
            class Device(SimulationDevice):
                def move(self,targets,ms):moves.append(targets);super().move(targets,ms)
            p=Profile.load(PROFILE);record=recording(p)
            script=iter([(0,'connect',(p,True,'unused')),(0,'play',(record,[1,7],.5,object())),
                         *[(t,None,None) for t in (.1,.201,.3,.401,.5,.601,.7,.801)],(.9,'shutdown',None)])
            class Commands:
                def get(self,timeout):
                    at,op,value=next(script);now[0]=at
                    if fail and at==.201:players[0].error=RuntimeError('sound device lost')
                    return op,value
            w=Worker(Commands(),events,threading.Event())
            with patch('shadow_play.bus_servo.audio.AudioPlayer',Player),patch('shadow_play.bus_servo.gui.SimulationDevice',Device),\
                 patch('shadow_play.bus_servo.gui.TeachingSession',side_effect=lambda p,d,directory:TeachingSession(p,d,directory,clock=lambda:now[0])),\
                 patch('shadow_play.bus_servo.device.time.monotonic',side_effect=lambda:now[0]):w.run()
            self.assertTrue(players[0].closed)
            self.assertEqual(len(moves),1 if fail else 4)
            self.assertEqual(len(players[0].segments),len(moves))


if __name__=='__main__':unittest.main()
