"""Feedback teaching and bounded playback, independent of the GUI toolkit."""
import json
from pathlib import Path
import time
from datetime import datetime

from .model import finite, new_recording, playback_plan, save_recording, validate_recording
from .protocol import ServoUnavailable

PLAYBACK_STALL_S = 1.0  # Same bound as the FPGA motion lease; never resume a long stall.


class PlaybackRejected(ValueError):
    """Playback was not started; the device connection is still usable."""


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
        self.ready_axes = set(profile.axes) if device.simulation else set()
        self.next_board_poll = 0
        self.cancel_requested = lambda: False

    def require_feedback(self, numbers):
        self.profile.select(numbers)
        if not set(numbers) <= self.ready_axes:
            raise ServoUnavailable('板子已连接，所选舵机尚未检测；供电后点击“检测所选舵机”。')

    def probe(self, numbers):
        if self.recording or self.playing:
            raise RuntimeError('请先结束录制或回放。')
        self.profile.select(numbers)
        self.ready_axes.clear()
        self.last_feedback.clear()
        rows = self.device.read(numbers) if self.device.simulation else self.device.probe(numbers)
        self.validate_feedback(numbers, rows)
        self.ready_axes = set(numbers)
        self.last_feedback.update(rows)
        self.next_poll = self.clock() + .15
        return rows

    def validate_feedback(self, numbers, rows):
        if set(rows) != set(numbers):
            raise ValueError('Feedback axis set mismatch')
        for n, row in rows.items():
            self.profile.axes[n].degrees(row['p'])
            finite(row['at'], 0, 1e12, 'Device acquisition timestamp')

    def read(self, numbers):
        self.require_feedback(numbers)
        rows = self.device.read(numbers)
        self.validate_feedback(numbers, rows)
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
        self.require_feedback(numbers)
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
        if getattr(self.device, 'adaptive_playback', True) is not True:
            raise PlaybackRejected('板端需要更新回放时长适配服务，请更新后重连；尚未发送回放目标。')
        self.continuous_playback = (not self.device.simulation and
                                   self.profile.data.get('playback_speed_limit_enabled', True) is False)
        if self.continuous_playback and (getattr(self.device,'continuous_playback',False) is not True or
                                         getattr(self.device,'playback_speed_limit_enabled',True) is not False):
            raise PlaybackRejected('板端尚未更新连续回放和取消回放限速设置，请更新并重开上位机；未发送目标。')
        try:
            validate_recording(record, self.profile, live=not self.device.simulation)
            plan = playback_plan(record, self.profile, numbers, speed)
        except ValueError as exc:
            raise PlaybackRejected(str(exc)) from exc
        before = self.read(numbers)
        for n in numbers:
            a = self.profile.axes[n]
            if abs(a.degrees(before[n]['p'])-a.degrees(record['samples'][0]['positions'][str(n)])) > 1.5:
                raise PlaybackRejected(f'{n}号与首帧相差超过1.5°，请先执行“缓慢到首帧”并等待到位。')
        self.plan, self.play_numbers, self.index = plan, numbers[:], 0
        self.play_start = self.clock()
        self.play_end = plan[-1][0] + plan[-1][2]/1000
        self.play_due = self.play_start
        self.last_play_tick = self.play_start
        self.segment_started = self.play_start
        self.segment_duration_ms = 0
        self.playing = True
        if self.continuous_playback:
            self.next_poll = self.clock()+.3

    def playback_elapsed(self):
        """Progress within accepted commands; never advance into an unsent one."""
        if not self.index:return 0.0
        due, _, duration = self.plan[self.index-1]
        fraction = min(1, max(0, self.clock()-self.segment_started) / (self.segment_duration_ms/1000))
        return due + duration/1000 * fraction

    def _tick_playback(self):
        now = self.clock()
        if self.cancel_requested():return None, False
        if now-self.last_play_tick > PLAYBACK_STALL_S:
            raise TimeoutError('电脑回放线程停顿超过1秒，已中止；请检查电脑或串口后重新开始。')
        rows, finished = None, False
        # One blocking RPC per tick gives Stop a chance between requests.
        # move() acknowledges after board-side validation and all selected
        # targets have been sent. Give the last axis its full arrival time.
        # In continuous mode a single successor is submitted early. The board
        # reads feedback while the current segment runs and gates its send.
        lead = .22 if self.continuous_playback and self.index < len(self.plan) else 0
        if now + lead + 1e-9 >= self.play_due:
            if self.index < len(self.plan):
                _, targets, duration = self.plan[self.index]
                if self.continuous_playback:
                    result = self.device.playback_step(targets,duration,first=self.index==0)
                    rows = result['positions']
                    self.validate_feedback(self.play_numbers,rows)
                    self.last_feedback.update(rows)
                else:
                    move = getattr(self.device, 'playback_move', self.device.move)
                    result = move(targets, duration)
                from .protocol import integer
                self.segment_duration_ms = integer(
                    result['duration_ms'] if isinstance(result, dict) else duration,
                    duration, 9999, 'Acknowledged duration')
                self.segment_started = self.clock()-(result['dispatch_age_s'] if self.continuous_playback else 0)
                self.play_due = self.segment_started + self.segment_duration_ms/1000
                self.index += 1
                if self.continuous_playback:
                    self.next_poll = self.clock()+.3
            else:
                rows = self.read(self.play_numbers)
                final = self.plan[-1][1]
                for n in self.play_numbers:
                    a = self.profile.axes[n]
                    if abs(a.degrees(rows[n]['p']) - a.degrees(final[str(n)])) > 2:
                        raise RuntimeError(f'{n}号未到末帧，回放到位验收未通过。')
                self.playing = False
                finished = True
                self.next_poll = self.clock() + .15
        elif now >= self.next_poll and (not self.continuous_playback or self.play_due-now > .4):
            rows = self.read(self.play_numbers)
            self.next_poll = self.clock() + .15
        elif not self.device.simulation and not self.continuous_playback and now >= self.next_board_poll:
            self.device.board_status()
            self.next_board_poll = self.clock() + .5
        if self.clock()-now > PLAYBACK_STALL_S:
            raise TimeoutError('回放通信停顿超过1秒，已中止；请检查电脑或串口后重新开始。')
        self.last_play_tick = self.clock()
        return rows, finished

    def tick(self, idle_numbers):
        if self.playing:return self._tick_playback()
        now = self.clock()
        if not self.device.simulation and now >= self.next_board_poll:
            self.device.board_status()
            self.next_board_poll = now + .5
        finished = False
        rows = None
        if now >= self.next_poll:
            numbers = self.record['selected'] if self.recording else (self.play_numbers if self.playing else idle_numbers)
            if not self.recording and not self.playing:
                numbers = [n for n in numbers if n in self.ready_axes]
            if not numbers:
                return None, finished
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
