"""Offline admission review for a loaded, attended recovery proposal.

No device imports or execution switch. Approval is necessary, not shaft feedback.
This does not change either incident lock or the unloaded recovery entry point.
"""
import argparse
import json
from pathlib import Path

STORY_START = (1470, 1212, 1425, 1514, 1416, 1740, 1730, 1250, 1770, 1740)
# Existing gimbal-only observations with the 10-degree inset, rounded inward.
# This outer bound does NOT certify attached-rod clearance. Tests compare it
# against servo_button_jog.load_button_limits() and the source observations.
PULSE_LIMITS = ((575,2425), (1204,2425), (575,2425), (871,1759), (1019,2425),
                (871,1759), (871,1907), (1241,1907), (1019,1981), (871,1759))


def review(plan):
    if not isinstance(plan, dict):
        return {'status': 'blocked', 'reasons': ['plan_object_required'],
                'hardware_executed': False, 'execution_available': False,
                'incident_locks_removed': False}
    reasons = []
    for key in ('operator_authorized', 'observer_ready', 'linkage_clearance_reviewed'):
        if plan.get(key) is not True:
            reasons.append(key + '_required')
    start = plan.get('start', {})
    if not isinstance(start, dict):
        start = {}
    # Stale command registers, image guesses and permission cannot establish pose.
    if start.get('basis') not in ('measured_joint_angles', 'observed_commanded_pose_unchanged'):
        reasons.append('verified_start_required')
    if start.get('axes_moved_since_verification') is not False:
        reasons.append('start_invalidated_or_unknown')
    if not isinstance(start.get('evidence'), str) or not start.get('evidence', '').strip():
        reasons.append('start_evidence_required')
    route = plan.get('route', {})
    if not isinstance(route, dict):
        route = {}
    target_id = route.get('target_id', 'assembly_center')
    target = ({'assembly_center': [1500]*10,
               'story_start_v3': list(STORY_START)}.get(target_id)
              if isinstance(target_id, str) else None)
    if target is None:
        reasons.append('unsupported_target')
    if route.get('loaded_path_reviewed') is not True:
        reasons.append('loaded_path_review_required')
    frames = route.get('frames_us')
    valid = (isinstance(frames, list) and len(frames) >= 2 and
             all(isinstance(row, list) and len(row) == 10 and
                 all(type(p) is int and 500 <= p <= 2500 for p in row)
                 for row in frames))
    if not valid:
        reasons.append('ten_axis_route_required')
    else:
        if any(not low <= value <= high for row in frames
               for value, (low, high) in zip(row, PULSE_LIMITS)):
            reasons.append('axis_inset_limit_exceeded')
        if frames[0] != start.get('pulses_us'):
            reasons.append('route_start_mismatch')
        if target is not None and frames[-1] != target:
            reasons.append('assembly_center_is_1500us' if target_id == 'assembly_center'
                           else 'story_start_target_mismatch')
        if any(abs(a-b) > 24 for left, right in zip(frames, frames[1:])
               for a, b in zip(left, right)):
            reasons.append('step_exceeds_24us')
    if route.get('frame_period_ms') != 20:
        reasons.append('reviewed_20ms_cadence_required')
    if valid and len(frames) * .02 > 60:
        reasons.append('route_exceeds_60_seconds')
    return {'status': 'blocked' if reasons else 'eligible_for_executor_review',
            'reasons': reasons, 'hardware_executed': False,
            'execution_available': False, 'incident_locks_removed': False,
            'note': 'Offline checks do not certify clearance or actual joint position.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan', type=Path)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text(encoding='utf-8-sig'))
    if not isinstance(plan, dict):
        parser.error('Plan must be an object')
    result = review(plan)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2 if result['reasons'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
