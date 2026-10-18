"""Nominal initial targets, not shaft feedback or a loaded-path calibration."""
import math

SCHEMA = 'servo-initial-pose-v1'
PINS = ('D14','D15','F13','G13','G14','G15','J14','E13','E14','E15')
RODS = ('人物左手','人物头部','人物右手','老虎头部','老虎尾部')
# Existing inward margins from the attended routes; these are NOT proof of a
# safe ten-axis combination or the path from an unknown physical position.
DEGREE_LIMITS = ((10,260),(95,260),(10,260),(50,170),(70,260),
                 (50,170),(50,190),(100,190),(70,200),(50,170))
DEFAULT_ANGLES = (135.,)*10


def nominal_pulse(angle):
    return int(math.floor(500+angle*2000/270+.5))


PULSE_LIMITS = tuple((nominal_pulse(lo),nominal_pulse(hi)) for lo,hi in DEGREE_LIMITS)


def angles_to_pulses(angles):
    if not isinstance(angles,(list,tuple)) or len(angles)!=10:
        raise ValueError('请填写完整的十路初始角度。')
    result=[]
    for i,(value,(lo,hi)) in enumerate(zip(angles,DEGREE_LIMITS),1):
        if isinstance(value,bool):
            raise ValueError(f'{i}号角度格式不正确。')
        angle=float(value)
        if not math.isfinite(angle) or not lo<=angle<=hi:
            raise ValueError(f'{i}号角度须在 {lo}–{hi}° 内；范围不是带杆安全保证。')
        result.append(nominal_pulse(angle))
    return result


def validate_pulses(pulses):
    if not isinstance(pulses,list) or len(pulses)!=10:
        raise ValueError('需要完整十路整数脉宽。')
    for i,(value,(lo,hi)) in enumerate(zip(pulses,PULSE_LIMITS),1):
        if type(value) is not int or not lo<=value<=hi:
            raise ValueError(f'{i}号目标超出既有内缩限制。')
    return pulses[:]


def encode_profile(angles):
    angles_to_pulses(angles)
    return dict(schema=SCHEMA,nominal_angles_deg=[float(x) for x in angles])


def decode_profile(profile):
    if not isinstance(profile,dict) or set(profile)!={'schema','nominal_angles_deg'} or profile['schema']!=SCHEMA:
        raise ValueError('不是十路初始角度配置文件。')
    angles_to_pulses(profile['nominal_angles_deg'])
    return [float(x) for x in profile['nominal_angles_deg']]
