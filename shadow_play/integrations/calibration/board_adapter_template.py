"""Copy to board_adapter_local.py and implement using YOUR verified board driver.

No register address, GPIO, PWM frequency or angle conversion is assumed here.
Construction and read_state must never issue a motion command.
"""


def create_driver(config):
    raise NotImplementedError('Connect the actual initialized motor driver before starting board_server.')


class Driver:
    def read_state(self):
        """Read the driver's full LAST-SUBMITTED state, without moving hardware.

        Return:
        {'adopted': [{'axis_id': ..., 'value': ..., 'unit': ...}, ...],
         'slides': [{'id': ..., 'value': ..., 'unit': ...,
                     'state_kind': 'commanded', 'controllable': True}, ...],
         'feedback': None}

        Never populate this from config initial values or a new sync request.
        If state is unknown after boot/fault, raise until operator initializes it.
        If slides are configured measured, use actual sensors and document origin.
        No encoder means feedback=None, not an echo of PWM commands.
        """
        raise NotImplementedError

    def apply_targets(self, axes, slides):
        """Apply one full group; return read_state() after successful submission.

        1. Verify IDs, units, limits, step limits, homing and mechanism constraints.
        2. Convert units only through documented hardware definitions.
        3. Submit through the existing PS driver/AXI/PL interfaces.
        4. Keep actual adopted values (after quantization) in the driver state.
        On partial failure, stop according to your verified policy, mark state
        unknown and raise. Do not claim the previous state is still valid.
        Enforce a bounded driver-call duration; do not retry uncertain motion.
        Hardware limits/watchdog must operate independently of this TCP server.
        """
        raise NotImplementedError
