"""Read-only playback display data; no device access or playback scheduling."""
from bisect import bisect_right

from .model import finite


def format_time(seconds):
    tenths = max(0, int(float(seconds) * 10 + 1e-6))
    minutes, remainder = divmod(tenths, 600)
    return f'{minutes:02d}:{remainder // 10:02d}.{remainder % 10}'


class PlaybackTimeline:
    def __init__(self, record, speed, duration=None, plan=None):
        self.speed = finite(speed, .1, 2, 'Playback speed')
        rows = record.get('samples', [])
        self.source_duration = max(0, rows[-1]['t'] - rows[0]['t']) if rows else 0
        self.duration = self.source_duration / self.speed if duration is None else duration
        self.playback_times = getattr(plan, 'playback_times', None)
        self.source_times = getattr(plan, 'source_times', None)
        self.retimed_intervals = getattr(plan, 'retimed_intervals', 0)
        self.speed_limited = getattr(plan,'speed_limited',True)
        if self.playback_times:
            self.duration = self.playback_times[-1]
        self.segments = record.get('segments_summary', [])
        self.ends = [segment['end_s'] for segment in self.segments]

    def snapshot(self, elapsed=0, state='ready', wall_elapsed=None):
        elapsed = min(self.duration, max(0, elapsed))
        source = min(self.source_duration, elapsed * self.speed)
        if self.playback_times:
            index = min(max(0,bisect_right(self.playback_times,elapsed)-1),len(self.playback_times)-2)
            start,end = self.playback_times[index:index+2]
            fraction = min(1,max(0,(elapsed-start)/(end-start)))
            source = self.source_times[index]+fraction*(self.source_times[index+1]-self.source_times[index])
        if state == 'completed':
            elapsed, source = self.duration, self.source_duration
        elif state == 'playing' and elapsed >= self.duration:
            state = 'checking'
        wall_elapsed = elapsed if wall_elapsed is None else max(elapsed,wall_elapsed)
        communication_delay = wall_elapsed-elapsed
        segment = ''
        if self.segments:
            index = min(bisect_right(self.ends, source), len(self.segments) - 1)
            segment = f'第 {index + 1}/{len(self.segments)} 段 · {self.segments[index]["name"]}'
        return dict(state=state, elapsed_s=wall_elapsed, duration_s=self.duration+communication_delay,
                    source_s=source, source_duration_s=self.source_duration,
                    speed=self.speed, fraction=elapsed/self.duration if self.duration else 0,
                    segment=segment, retimed_intervals=self.retimed_intervals,
                    speed_limited=self.speed_limited,
                    communication_delay_s=communication_delay)
