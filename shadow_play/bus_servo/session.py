"""Feedback teaching and bounded playback, independent of the GUI toolkit."""
import json
from pathlib import Path
import time
from datetime import datetime

from .model import finite, new_recording, playback_plan, save_recording, validate_recording


class TeachingSession:
    def __init__(self, profile, device, directory, clock=time.monotonic):
        self.profile, self.device, self.clock = profile, device, clock
        self.directory = Path(directory)
        self.record = None
        self.recording = False
        self.teaching = False
        self.playing = False
        self.journal = None
        self.last_path = None
        self.last_feedback = {}
        self.plan = []
        self.index = 0
        self.next_poll = 0
        self.rate = 10
        self.device.connect()

    def read(self, numbers):
        rows = self.device.read(numbers)
        if set(rows) != set(numbers):
            raise ValueError('Feedback axis set mismatch')
        for n, row in rows.items():
            self.profile.axes[n].degrees(row['p'])
            finite(row['at'], 0, 1e12, 'Device acquisition timestamp')
        self.last_feedback.update(rows)
        return rows

    def set_angles(self, numbers, angles, duration_ms):
        if self.playing or (self.recording and self.teaching):
            raise RuntimeError('手动示教或回放中不能发送角度。')
        axes = self.profile.select(numbers)
        targets = {str(a.number): a.position(angles[str(a.number)]) for a in axes}
        return self.move(targets, duration_ms)

    def capture_pose(self, numbers):
        if self.recording or self.playing:
            raise RuntimeError('请先结束连续录制/回放，再逐步录入姿势。')
        from .editing import PoseCaptureError, capture_pose
        rows = self.read(numbers)
        try:
            return capture_pose(self.profile, numbers, rows, self.device.simulation)
        except ValueError as exc:
            raise PoseCaptureError(str(exc)) from exc

    def move(self, targets, duration_ms):
        from .protocol import integer
        integer(duration_ms, 20, 9999, 'Duration')
        before = self.read([int(n) for n in targets])
        for key, p in targets.items():
            a = self.profile.axes[int(key)]
            a.check_position(p)
            delta = abs(a.degrees(p) - a.degrees(before[a.number]['p']))
            if delta > a.max_speed * duration_ms / 1000 + .2:
                raise ValueError(f'{a.number}号速度过快，请增加到达时间。')
        self.device.move(targets, duration_ms)

    def start_recording(self, numbers, rate=10, teaching=True):
        if self.recording or self.playing:
            raise RuntimeError('请先结束当前录制或回放。')
        self.profile.select(numbers)
        finite(rate, 5, 20, 'Rate')
        self.rate = rate
        self.record = new_recording(self.profile, numbers, self.device.simulation, rate)
        self.record['mode'] = 'hand_teaching' if teaching else 'controlled_feedback'
        self.directory.mkdir(parents=True, exist_ok=True)
        self.take_name = 'take_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        self.journal = (self.directory / (self.take_name + '.jsonl')).open('x', encoding='utf-8')
        try:
            self.journal.write(json.dumps({'header': self.record}, ensure_ascii=False) + '\n')
            self.journal.flush()
        except BaseException:
            self.journal.close(); self.journal = None
            raise
        self.recording, self.teaching = True, teaching
        if teaching:
            self.device.release(numbers)
        self.origin = None
        self.next_poll = 0

    def finish_recording(self, complete=True, reason='operator_finished'):
        if not self.recording:
            return self.last_path
        self.recording = False
        self.record['complete'] = complete and len(self.record['samples']) >= 2
        self.record['end_reason'] = reason
        samples = self.record['samples']
        if len(samples) >= 2:
            self.record['measured_hz'] = (len(samples)-1) / (samples[-1]['t']-samples[0]['t'])
            self.record['max_sample_gap_s'] = max(b['t']-a['t'] for a,b in zip(samples,samples[1:]))
        try:
            self.last_path = self.directory / (self.take_name + '.json')
            save_recording(self.last_path, self.record)
            return self.last_path
        finally:
            if self.journal:
                self.journal.close(); self.journal = None

    def prepare_first(self, record, numbers):
        if self.recording or self.playing:
            raise RuntimeError('请先结束录制/回放。')
        validate_recording(record, self.profile, live=not self.device.simulation)
        self.profile.select(numbers)
        if not set(numbers) <= set(record['selected']):
            raise ValueError('所选轴没有录入此轨迹。')
        targets = {str(n): record['samples'][0]['positions'][str(n)] for n in numbers}
        before = self.read(numbers)
        seconds = max(2, max(abs(self.profile.axes[n].degrees(targets[str(n)])-
                                  self.profile.axes[n].degrees(before[n]['p'])) /
                                  self.profile.axes[n].max_speed for n in numbers) + .2)
        if seconds > 9.999:
            raise ValueError('距离首帧太远；请分步设置角度接近起点。')
        self.move(targets, round(seconds*1000))
        return seconds

    def start_playback(self, record, numbers, speed=.5):
        if self.recording or self.playing:
            raise RuntimeError('请先结束录制/回放。')
        validate_recording(record, self.profile, live=not self.device.simulation)
        plan = playback_plan(record, self.profile, numbers, speed)
        before = self.read(numbers)
        for n in numbers:
            a = self.profile.axes[n]
            if abs(a.degrees(before[n]['p'])-a.degrees(record['samples'][0]['positions'][str(n)])) > 1.5:
                raise ValueError(f'{n}号与首帧相差超过1.5°，请先执行“缓慢到首帧”并等待到位。')
        self.plan, self.play_numbers, self.index = plan, numbers[:], 0
        self.play_start = self.clock()
        self.play_end = plan[-1][0] + plan[-1][2]/1000
        self.playing = True

    def tick(self, idle_numbers):
        now = self.clock()
        finished = False
        if self.playing:
            elapsed = now - self.play_start
            if self.index < len(self.plan):
                due, targets, duration = self.plan[self.index]
                if elapsed >= due:
                    if elapsed - due > min(.15, duration / 2000):
                        raise TimeoutError('回放调度落后，已中止；不会追赶式连发。请降低速度。')
                    self.device.move(targets, duration)
                    self.index += 1
            elif elapsed >= self.play_end:
                rows = self.read(self.play_numbers)
                final = self.plan[-1][1]
                for n in self.play_numbers:
                    a = self.profile.axes[n]
                    if abs(a.degrees(rows[n]['p']) - a.degrees(final[str(n)])) > 2:
                        raise RuntimeError(f'{n}号未到末帧，回放到位验收未通过。')
                self.playing = False
                finished = True
        rows = None
        if now >= self.next_poll:
            numbers = self.record['selected'] if self.recording else (self.play_numbers if self.playing else idle_numbers)
            rows = self.read(numbers)
            self.next_poll = now + (1/self.rate if self.recording else .15)
            if self.recording:
                acquired = [row['at'] for row in rows.values()]
                if max(acquired)-min(acquired) > .5:
                    raise TimeoutError('本帧各轴采样间隔过大，不能视为完整轨迹帧。')
                if self.origin is None:
                    self.origin = min(acquired)
                t = max(acquired) - self.origin
                if t > 3600 or len(self.record['samples']) >= 100000:
                    raise RuntimeError('已到单次录制上限。')
                previous = self.record['samples'][-1]['t'] if self.record['samples'] else None
                if previous is not None and (t <= previous or t-previous > .5):
                    raise TimeoutError('反馈时间倒退或出现超过0.5秒空档，录制已中断。')
                sample = {'t': t, 'positions': {str(n):row['p'] for n,row in rows.items()},
                          'axis_t': {str(n):row['at']-self.origin for n,row in rows.items()}}
                self.record['samples'].append(sample)
                self.journal.write(json.dumps(sample, separators=(',', ':'), allow_nan=False)+'\n')
                self.journal.flush()
        return rows, finished

    def stop(self, reason='operator_stopped'):
        self.playing = False
        try:
            if self.recording:
                self.finish_recording(complete=False, reason=reason)
        finally:
            stopped = self.device.stop()
        return stopped

    def close(self):
        try:
            if self.recording:
                self.finish_recording(complete=False, reason='connection_closed')
        finally:
            self.device.close()
