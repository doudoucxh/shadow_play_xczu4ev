"""Attended 27–34 s soundtrack trial with the existing FAST tiger route.

No arbitrary choreography, automatic repeats, lock removal or full-show claim.
PCM RUNNING observation gives an approximate onset, not measured acoustic latency.
"""
import hashlib
from pathlib import Path
import subprocess
import time

CLIP = '/tmp/tiger-27-34-20261014.mp3'
CLIP_SHA = '19343f2d125993308718ef1db58a9bc5b074a315296fcf8d8664153bae535c1d'
PLAYER = '/tmp/audio-player-20261014/usb_audio_play'
PCM_STATUS = Path('/proc/asound/card1/pcm0p/sub0/status')


class AudioClip:
    def __init__(self):
        if hashlib.sha256(Path(CLIP).read_bytes()).hexdigest() != CLIP_SHA:
            raise RuntimeError('Wrong 27–34 second audio segment')
        if 'Jieli' not in Path('/proc/asound/cards').read_text():
            raise RuntimeError('USB speaker not present')
        if 'closed' not in PCM_STATUS.read_text():
            raise RuntimeError('Playback PCM already in use')
        self.proc = None
        self.finished = False

    def start(self, device, sleep):
        self.proc = subprocess.Popen([PLAYER, '1', '0', '.75', CLIP],
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        deadline = device.clock()+3
        while device.clock() < deadline:
            device.check()
            if self.proc.poll() is not None:
                raise RuntimeError('Audio exited before PCM RUNNING')
            if 'RUNNING' in PCM_STATUS.read_text():
                return device.clock()
            device.wait(.01, sleep)
        raise RuntimeError('No audio start within three seconds')

    def check(self):
        if self.proc is None or self.finished:
            return
        code = self.proc.poll()
        if code is not None:
            output = self.proc.communicate()[0].decode('utf-8', errors='replace')
            if code != 0 or 'PLAY_COMPLETE' not in output:
                raise RuntimeError('USB playback failed: '+output[-500:])
            self.finished = True
            self.output = output

    def close(self):
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=.5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=.5)


def run_segment(d, emit, sleep=time.sleep, audio_factory=AudioClip):
    normal = False
    audio = None
    original_check = d.check
    try:
        if d.plan['profile'] != 'tiger-operator-low-rear-fast':
            raise ValueError('Only existing FAST route is supported')
        audio = audio_factory()  # Validate audio before enabling any output.
        state = d.adopt(d.plan['expected_pulses_us'][:])
        emit(dict(event='reference_held', profile=d.plan['profile'], route_sha256=d.route_sha256,
                  tempo_step_us=8, state=state, position_feedback=None,
                  startup_is_not_rate_limited=True, incident_locks_removed=False))
        while True:
            d.check()
            if d.host.action is not None:
                action, sequence = d.host.action
                d.host.action = None
                if action != 'demo' or sequence != d.sequence:
                    raise RuntimeError('Fresh static review required')
                break
            d.wait(.03, sleep)
        def guarded_check():
            audio.check()
            return original_check()
        d.check = guarded_check
        onset = audio.start(d, sleep)
        emit(dict(event='audio_running_observed', clip_original_start_s=27,
                  board_monotonic_onset=onset, acoustic_latency_measured=False,
                  synchronization='observed_PCM_running_plus_monotonic_clock'))
        d.wait(max(0, onset+2-d.clock()), sleep)
        emit(dict(event='operator_trial_started', state=d.status(),
                  estimated_audio_time_s=27+d.clock()-onset,
                  static_reference_visually_reviewed=True))
        # Existing exact route, step limits, holds, host leases and hardware guards.
        holds = (0, .09, .09, .04, .1, .05, .025, .075)
        for stage in range(1, len(d.targets)):
            d.advance(stage, emit, sleep)
            d.wait(holds[stage], sleep)
        emit(dict(event='operator_trial_complete', state=d.status(),
                  estimated_audio_time_s=27+d.clock()-onset, automatic_replay_allowed=False))
        while not audio.finished:
            d.check()
            if d.clock()-onset > 8:
                raise RuntimeError('Audio completion overdue')
            d.wait(.02, sleep)
        emit(dict(event='audio_segment_complete', player_output=audio.output,
                  original_audio_range_s=[27,34], full_show_executed=False))
        normal = True
    finally:
        # Stop motion first, even if audio cleanup itself fails.
        d.check = original_check
        try:
            state = d.stop_after_frame() if normal else d.off()
            emit(dict(event='outputs_off', state=state, normal_frame_stop=normal,
                      incident_locks_removed=False))
        finally:
            if audio is not None:
                audio.close()


if __name__ == '__main__':
    import tiger_leap_session_20261014_r12 as actor
    actor.run = run_segment
    actor.main()
