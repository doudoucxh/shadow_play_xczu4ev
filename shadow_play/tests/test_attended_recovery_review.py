import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'integrations/calibration'))
from attended_recovery_review import review


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.plan = dict(operator_authorized=True, observer_ready=True,
                         linkage_clearance_reviewed=True,
                         start=dict(basis='observed_commanded_pose_unchanged',
                                    axes_moved_since_verification=False,
                                    evidence='fixture-only: witnessed pose', pulses_us=[1490]*10),
                         route=dict(loaded_path_reviewed=True, frame_period_ms=20,
                                    frames_us=[[1490]*10, [1500]*10]))

    def test_review_never_enables_execution(self):
        result = review(self.plan)
        self.assertEqual(result['status'], 'eligible_for_executor_review')
        self.assertFalse(result['execution_available'])
        self.assertFalse(result['incident_locks_removed'])

    def test_authorization_does_not_override_manual_movement(self):
        self.plan['start']['axes_moved_since_verification'] = True
        self.assertIn('start_invalidated_or_unknown', review(self.plan)['reasons'])

    def test_register_or_visual_guess_not_feedback(self):
        for basis in ('register_readback', 'visual_estimate', None):
            self.plan['start']['basis'] = basis
            self.assertIn('verified_start_required', review(self.plan)['reasons'])

    def test_reject_zero_center_large_jump_and_wrong_start(self):
        for final, reason in [([0]*10, 'ten_axis_route_required'),
                              ([1600]*10, 'step_exceeds_24us')]:
            p = copy.deepcopy(self.plan)
            p['route']['frames_us'][-1] = final
            self.assertIn(reason, review(p)['reasons'])
        self.plan['start']['pulses_us'] = [1400]*10
        self.assertIn('route_start_mismatch', review(self.plan)['reasons'])

    def test_missing_attendance_and_route_review_rejected(self):
        self.plan['observer_ready'] = False
        self.plan['route']['loaded_path_reviewed'] = False
        self.assertIn('observer_ready_required', review(self.plan)['reasons'])
        self.assertIn('loaded_path_review_required', review(self.plan)['reasons'])


if __name__ == '__main__':
    unittest.main()
