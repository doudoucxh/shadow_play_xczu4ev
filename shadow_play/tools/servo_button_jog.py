"""Host-side, bounded button increments; never opens serial or enables PWM."""
import json
import math
from pathlib import Path

OBSERVATIONS = Path(__file__).resolve().parents[1] / 'config/servo_gimbal_observations.20261010.json'
MARGIN_DEGREES = 10
STEP_US = 8  # About 1.08 nominal degrees: twice the original step, same cadence.
INTERVAL_MS = 200  # Starts after the previous acknowledgement; no catch-up burst.
PINS = ('D14', 'D15', 'F13', 'G13', 'G14', 'G15', 'J14', 'E13', 'E14', 'E15')


def load_button_limits(path=OBSERVATIONS):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if data.get('test_stage') != 'gimbal_brackets_installed_rods_disconnected':
        raise ValueError('Button limits require the recorded gimbal-only observations')
    channels = data['channels']
    if len(channels) != 10:
        raise ValueError('Ten channel observations required')
    limits = {}
    for number, channel in enumerate(channels, 1):
        if channel['number'] != number or channel['pin'] != PINS[number-1]:
            raise ValueError('Channel/pin mismatch in button limits')
        low, high = channel['reported_range_degrees']
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in (low, high)):
            raise ValueError('Finite numeric limits required')
        if not 0 <= low < high <= 270 or high-low <= 2*MARGIN_DEGREES:
            raise ValueError('Invalid observed range')
        low, high = low+MARGIN_DEGREES, high-MARGIN_DEGREES
        # Round inward so adopted integer microseconds stay inside the margin.
        limits[number] = (math.ceil(500+low*2000/270), math.floor(500+high*2000/270))
    return limits


def checked_target(limits, channel, pulse):
    if type(channel) is not int or channel not in limits or type(pulse) is not int:
        raise ValueError('Invalid channel or pulse')
    low, high = limits[channel]
    if not low <= pulse <= high:
        raise ValueError('目标超出本路按钮模式的内缩范围；不会自动跳回范围内。')
    return pulse


def next_button_pulse(limits, channel, pulse, direction):
    checked_target(limits, channel, pulse)
    if type(direction) is not int or direction not in (-1, 1):
        raise ValueError('Direction must be -1 or +1')
    low, high = limits[channel]
    return min(high, max(low, pulse+direction*STEP_US))
