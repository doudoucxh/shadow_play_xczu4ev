"""Read-only playback display data; no device access or playback scheduling."""
from bisect import bisect_right

from .model import finite


def format_time(seconds):
    tenths = max(0, int(float(seconds) * 10 + 1e-6))
    minutes, remainder = divmod(tenths, 600)
    return f'{minutes:02d}:{remainder // 10:02d}.{remainder % 10}'


class PlaybackTimeline:
    def __init__(self, record, speed, duration=None):
        self.speed = finite(speed, .1, 2, 'Playback speed')
        rows = record.get('samples', [])
        self.source_duration = max(0, rows[-1]['t'] - rows[0]['t']) if rows else 0
        self.duration = self.source_duration / self.speed if duration is None else duration
        self.segments = record.get('segments_summary', [])
        self.ends = [segment['end_s'] for segment in self.segments]

    def snapshot(self, elapsed=0, state='ready'):
        elapsed = min(self.duration, max(0, elapsed))
        source = min(self.source_duration, elapsed * self.speed)
        if state == 'completed':
            elapsed, source = self.duration, self.source_duration
        elif state == 'playing' and elapsed >= self.duration:
            state = 'checking'
        segment = ''
        if self.segments:
            index = min(bisect_right(self.ends, source), len(self.segments) - 1)
            segment = f'第 {index + 1}/{len(self.segments)} 段 · {self.segments[index]["name"]}'
        return dict(state=state, elapsed_s=elapsed, duration_s=self.duration,
                    source_s=source, source_duration_s=self.source_duration,
                    speed=self.speed, fraction=source/self.source_duration if self.source_duration else 0,
                    segment=segment)
