#pragma once

#include <array>
#include <cstddef>
#include <string>
#include <vector>

namespace shadow {

// Names describe the puppet's own left/right, not the viewer's left/right.
enum class RodId : std::size_t {
    WusongNeck = 0,  // Physical attachment at Wusong's neck.
    WusongBody = WusongNeck,  // Legacy source alias; output uses wusong_neck.
    WusongLeft,
    WusongRight,
    TigerHead,  // Physical attachment at the tiger's ear.
    TigerTail,
    Count
};
constexpr std::size_t kRodCount = static_cast<std::size_t>(RodId::Count);

const char* rod_name(RodId rod);
RodId parse_rod_name(const std::string& name);

struct RodTarget {
    // Normalized rod target: center=(0,0), x right, y up, each in [-1,1].
    // These are desired rod movements, NOT raw human skeleton landmarks.
    double x = 0.0;
    double y = 0.0;
    bool valid = false;
};

struct ShadowPose {
    std::array<RodTarget, kRodCount> rods{};
    RodTarget& at(RodId rod);
    const RodTarget& at(RodId rod) const;
};

// Utility for an already-selected rod point in a unit screen coordinate space.
// x/y outside [0,1] are intentionally left for the mapper to clamp and report.
// This is not human-to-puppet retargeting or mirror correction.
RodTarget from_unit_screen(double x, double y, bool valid = true);

struct AxisCalibration {
    std::string axis_id;
    RodId rod = RodId::WusongNeck;
    double neutral_deg = 0.0;
    double min_deg = 0.0;
    double max_deg = 0.0;
    // Initial local linear model:
    // angle = neutral + gain_x*x + gain_y*y, before angle/rate limiting.
    double gain_x_deg = 0.0;
    double gain_y_deg = 0.0;
    double max_speed_deg_s = 0.0;
    // 0 disables the low-pass filter; rate limiting always remains enabled.
    double smoothing_tau_s = 0.0;
};

void validate_calibrations(const std::vector<AxisCalibration>& axes);

struct MapperOptions {
    // Keep using the last valid point for this long, then move toward neutral.
    double input_hold_s = 0.30;
    // After a scheduling stall, do not make a large catch-up angle step.
    double max_step_s = 0.05;
};

enum class InputState {
    NoInput,
    TrackingOrHolding,
    ReturningToNeutral,
    CommandHeld
};
const char* input_state_name(InputState state);

struct AxisOutput {
    std::string axis_id;
    RodId rod = RodId::WusongNeck;
    double angle_deg = 0.0;           // Send this limited command to the backend.
    double limited_target_deg = 0.0;  // Diagnostic only: before filter/rate limit.
    InputState input_state = InputState::NoInput;
    bool input_clamped = false;
    bool angle_limited = false;
    bool speed_limited = false;
};

// Stateful, single-threaded core. Route all input and step calls through one
// control thread. It performs no device I/O and has no source-mode dependency.
class MotionMapper {
public:
    // Initial commands must come from an initialized/homed backend (or a
    // simulator). They are NOT inferred physical motor positions.
    MotionMapper(std::vector<AxisCalibration> axes,
                 const std::vector<double>& initial_commands_deg,
                 MapperOptions options = {},
                 double start_time_s = 0.0);

    // Call ONCE per newly received frame, using local monotonic arrival time.
    // Invalid/non-finite rods do not refresh their last-good timestamp.
    // Returns the number of accepted rods; out-of-range finite points clamp.
    std::size_t submit_pose(const ShadowPose& pose, double arrival_time_s);

    // Use on a mode change/explicit stop to discard previous-mode inputs.
    // Subsequent step() calls smoothly return toward neutral unless fresh
    // inputs are submitted. This is not a hardware emergency stop.
    void clear_inputs(double now_s);

    // Call at the control cadence even when the input stream has stopped.
    // All timestamps must use the same clock and never move backwards.
    std::vector<AxisOutput> step(double now_s);

    // Keep the last command exactly during an intentional show pause. Advances
    // the control clock without refreshing input age or inventing new poses.
    std::vector<AxisOutput> hold(double now_s);

    const std::vector<AxisCalibration>& axes() const noexcept { return axes_; }

private:
    struct LastRod {
        double x = 0.0;
        double y = 0.0;
        double last_good_s = 0.0;
        bool available = false;
        bool clamped = false;
    };
    void check_event_time(double now_s) const;

    std::vector<AxisCalibration> axes_;
    std::vector<double> commands_deg_;
    std::array<LastRod, kRodCount> last_rods_{};
    MapperOptions options_;
    double last_step_s_ = 0.0;
    double last_event_s_ = 0.0;
};

}  // namespace shadow
