"""Local PCM assets and a short-buffer Windows player driven by motion time."""
import ctypes as ct
from ctypes import wintypes as wt
import hashlib
import os
from pathlib import Path
import shutil
import struct
import subprocess
import threading
import time
from uuid import uuid4
import wave

import numpy as np

RATE=48000
MAX_BYTES=384*1024*1024


def file_sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def wav_info(path):
    with wave.open(str(path),'rb') as w:
        if w.getnchannels()!=2 or w.getsampwidth()!=2 or w.getframerate()!=RATE or w.getcomptype()!='NONE':
            raise ValueError('音频素材格式不是48kHz / 双声道 / 16位PCM。')
        frames=w.getnframes()
    if not .02<=frames/RATE<=1800 or Path(path).stat().st_size>MAX_BYTES:
        raise ValueError('单个音频需为0.02秒～30分钟，且转换后不超过384MB。')
    with Path(path).open('rb') as stream:
        if stream.read(4)!=b'RIFF':raise ValueError('音频RIFF头无效。')
        stream.seek(12)
        while True:
            header=stream.read(8)
            if len(header)!=8:raise ValueError('音频数据块缺失。')
            kind,size=struct.unpack('<4sI',header)
            if kind==b'data':return frames,stream.tell()
            stream.seek(size+(size%2),1)


def verify_asset(asset):
    path=Path(asset['file'])
    if not path.is_file():raise FileNotFoundError('找不到音频素材，请将工程与同名.assets文件夹放在一起：'+path.name)
    frames,offset=wav_info(path)
    if file_sha(path)!=asset['sha256'] or abs(frames/RATE-asset['duration_s'])>1e-7:
        raise ValueError('音频素材已改变或不完整，请重新导入。')
    return frames,offset


def import_audio(path, directory):
    path=Path(path).resolve();directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    if path.stat().st_size>MAX_BYTES:raise ValueError('音频源文件超过384MB。')
    ffmpeg=shutil.which('ffmpeg')
    temporary=directory/(uuid4().hex+'.wav')
    try:
        if ffmpeg:
            result=subprocess.run([ffmpeg,'-nostdin','-hide_banner','-loglevel','error','-i',str(path),
                '-map','0:a:0','-vn','-ac','2','-ar',str(RATE),'-c:a','pcm_s16le','-t','1800.001',str(temporary)],
                capture_output=True,timeout=120,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if result.returncode:raise ValueError('音频无法解码：'+result.stderr.decode('utf-8','replace')[-600:])
        else:
            wav_info(path);shutil.copyfile(path,temporary)
        frames,offset=wav_info(temporary);key=file_sha(temporary);target=directory/(key+'.wav')
        if target.exists():
            if file_sha(target)!=key:raise ValueError('本地音频素材库摘要不一致。')
            temporary.unlink()
        else:temporary.replace(target)
        pcm=np.memmap(target,dtype='<i2',mode='r',offset=offset,shape=(frames,2))
        buckets=np.linspace(0,frames,min(1200,frames)+1,dtype=int)
        peaks=[round(float(np.abs(pcm[a:b].astype(np.int32)).max())/32768,4) for a,b in zip(buckets,buckets[1:])]
        del pcm
        return dict(file=str(target.resolve()),sha256=key,name=path.stem[:120],
                    duration_s=frames/RATE,sample_rate=RATE,channels=2,peaks=peaks)
    finally:
        if temporary.exists():temporary.unlink()


class AudioTrack:
    def __init__(self, project):
        self.clips=[dict(c) for c in project['clips'] if c['kind']=='audio']
        self.sources={}
        for key in {c['source_id'] for c in self.clips}:
            asset=project['audio_sources'][key];frames,offset=verify_asset(asset)
            self.sources[key]=np.memmap(asset['file'],dtype='<i2',mode='r',offset=offset,shape=(frames,2))

    def render(self, times, active=None):
        times=np.asarray(times);out=np.zeros((len(times),2),dtype=np.float64)
        for c in self.clips:
            end=c['at_s']+(c['out_s']-c['in_s'])/c['speed']
            mask=(times>=c['at_s'])&(times<end)
            if active is not None:mask &= active
            if not mask.any():continue
            pcm=self.sources[c['source_id']]
            x=(c['in_s']+(times[mask]-c['at_s'])*c['speed'])*RATE
            x=np.clip(x,0,len(pcm)-1);i=x.astype(np.int64);f=(x-i)[:,None]
            out[mask]+=(pcm[i]*(1-f)+pcm[np.minimum(i+1,len(pcm)-1)]*f)*c.get('gain',1)
        return np.clip(out,-32768,32767).astype('<i2').tobytes()


class WaveSink:
    """WinMM waveOut with at most three 20ms PCM buffers."""
    def __init__(self):
        if os.name!='nt':raise RuntimeError('电脑音频播放当前需要Windows。')
        class Format(ct.Structure):
            _pack_=1
            _fields_=[('tag',wt.WORD),('channels',wt.WORD),('rate',wt.DWORD),('bytes_s',wt.DWORD),
                      ('align',wt.WORD),('bits',wt.WORD),('extra',wt.WORD)]
        class Header(ct.Structure):
            _fields_=[('data',ct.c_void_p),('size',wt.DWORD),('recorded',wt.DWORD),('user',ct.c_size_t),
                      ('flags',wt.DWORD),('loops',wt.DWORD),('next',ct.c_void_p),('reserved',ct.c_size_t)]
        self.Header=Header;self.dll=ct.WinDLL('winmm');self.handle=ct.c_void_p();self.buffers=[]
        self.dll.waveOutOpen.argtypes=[ct.POINTER(ct.c_void_p),wt.UINT,ct.POINTER(Format),ct.c_size_t,ct.c_size_t,wt.DWORD]
        for name in ('waveOutPrepareHeader','waveOutWrite','waveOutUnprepareHeader'):
            getattr(self.dll,name).argtypes=[ct.c_void_p,ct.POINTER(Header),wt.UINT]
        for name in ('waveOutReset','waveOutClose'):getattr(self.dll,name).argtypes=[ct.c_void_p]
        fmt=Format(1,2,RATE,RATE*4,4,16,0)
        self.check(self.dll.waveOutOpen(ct.byref(self.handle),0xffffffff,ct.byref(fmt),0,0,0))

    @staticmethod
    def check(code):
        if code:raise RuntimeError(f'电脑音频设备错误 {code}；请检查默认扬声器。')

    def pending(self):
        while self.buffers and self.buffers[0][1].flags&1:
            data,header=self.buffers.pop(0)
            self.check(self.dll.waveOutUnprepareHeader(self.handle,ct.byref(header),ct.sizeof(header)))
        return len(self.buffers)

    def write(self, pcm):
        data=ct.create_string_buffer(pcm);header=self.Header(ct.cast(data,ct.c_void_p),len(pcm),0,0,0,0,None,0)
        self.check(self.dll.waveOutPrepareHeader(self.handle,ct.byref(header),ct.sizeof(header)))
        self.buffers.append((data,header))
        self.check(self.dll.waveOutWrite(self.handle,ct.byref(header),ct.sizeof(header)))

    def close(self):
        if self.handle:
            self.dll.waveOutReset(self.handle)
            for data,header in self.buffers:self.dll.waveOutUnprepareHeader(self.handle,ct.byref(header),ct.sizeof(header))
            self.buffers.clear();self.dll.waveOutClose(self.handle);self.handle=ct.c_void_p()


class AudioPlayer:
    def __init__(self, track, sink_factory=WaveSink, clock=time.monotonic):
        self.track=track;self.clock=clock;self.sink=sink_factory()
        self.lock=threading.Lock();self.mapper=None;self.error=None;self.stopped=threading.Event()
        self.thread=threading.Thread(target=self._run,daemon=True);self.thread.start()

    def segment(self, start, end, wall_start, seconds):
        # Only accepted motion segments authorize audio time advancement.
        def mapper(wall):
            f=(wall-wall_start)/seconds
            return start+np.clip(f,0,1)*(end-start),(f>=0)&(f<1)
        with self.lock:self.mapper=mapper

    def preview(self, playback_times, source_times, wall_start, offset=0):
        total=playback_times[-1]
        def mapper(wall):
            t=wall-wall_start+offset
            return np.interp(t,playback_times,source_times),(t>=0)&(t<total)
        with self.lock:self.mapper=mapper

    def _run(self):
        try:
            while not self.stopped.is_set():
                pending=self.sink.pending()
                if pending>=3:self.stopped.wait(.004);continue
                with self.lock:mapper=self.mapper
                if mapper is None:self.stopped.wait(.004);continue
                wall=self.clock()+pending*.02+np.arange(960)/RATE
                source,active=mapper(wall)
                # Do not queue silence across an unknown next motion segment:
                # it would mask the beginning of the next sound after its ACK.
                if not active.any():self.stopped.wait(.004);continue
                pcm=self.track.render(source,active)
                self.sink.write(pcm)
        except Exception as exc:self.error=exc
        finally:self.sink.close()

    def close(self, wait=True):
        self.stopped.set()
        if wait:self.thread.join(timeout=1)


def export_wav(path, track, duration_s):
    path=Path(path)
    with path.open('xb') as stream, wave.open(stream,'wb') as w:
        w.setnchannels(2);w.setsampwidth(2);w.setframerate(RATE)
        frames=round(duration_s*RATE)
        for start in range(0,frames,RATE):w.writeframes(track.render(np.arange(start,min(frames,start+RATE))/RATE))
