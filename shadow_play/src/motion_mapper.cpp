#include "shadow/motion_mapper.hpp"

#include <algorithm>
#include <cmath>
#include <set>
#include <stdexcept>
#include <utility>

namespace shadow {
namespace {
constexpr const char* kRodNames[] = {
    "wusong_neck", "wusong_left", "wusong_right", "tiger_head", "tiger_tail"
};

std::size_t rod_index(RodId rod) {
    const auto index = static_cast<std::size_t>(rod);
    if (index >= kRodCount) {
        throw std::invalid_argument("invalid rod ID");
    }
    return index;
}

bool valid_axis_id(const std::string& id) {
    if (id.empty()) return false;
    for (const char c : id) {
        if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
              (c >= '0' && c <= '9') || c == '_' || c == '-')) return false;
    }
    return true;
}
}  // namespace

const char* rod_name(RodId rod) { return kRodNames[rod_index(rod)]; }

RodId parse_rod_name(const std::string& name) {
    if (name == "wusong_body") return RodId::WusongNeck;  // Older scripts/configs.
    for (std::size_t i = 0; i < kRodCount; ++i) {
        if (name == kRodNames[i]) return static_cast<RodId>(i);
    }
    throw std::invalid_argument("unknown rod name: " + name);
}

RodTarget& ShadowPose::at(RodId rod) { return rods[rod_index(rod)]; }
const RodTarget& ShadowPose::at(RodId rod) const { return rods[rod_index(rod)]; }

RodTarget from_unit_screen(double x, double y, bool valid) {
    if (!valid || !std::isfinite(x) || !std::isfinite(y)) return {};
    const double normalized_x = 2.0 * x - 1.0;
    const double normalized_y = 1.0 - 2.0 * y;
    if (!std::isfinite(normalized_x) || !std::isfinite(normalized_y)) return {};
    return {normalized_x, normalized_y, true};
}

void validate_calibrations(const std::vector<AxisCalibration>& axes) {
    if (axes.empty()) throw std::invalid_argument("at least one axis is required");
    std::set<std::string> ids;
    for (const auto& axis : axes) {
        if (!valid_axis_id(axis.axis_id)) {
            throw std::invalid_argument("axis ID must contain letters, digits, '_' or '-'");
        }
        if (!ids.insert(axis.axis_id).second) {
            throw std::invalid_argument("duplicate axis ID: " + axis.axis_id);
        }
        rod_index(axis.rod);
        const double values[] = {axis.neutral_deg, axis.min_deg, axis.max_deg,
                                 axis.gain_x_deg, axis.gain_y_deg,
                                 axis.max_speed_deg_s, axis.smoothing_tau_s};
        for (const double value : values) {
            if (!std::isfinite(value)) {
                throw std::invalid_argument("non-finite calibration: " + axis.axis_id);
            }
        }
        if (!(axis.min_deg < axis.max_deg) ||
            axis.neutral_deg < axis.min_deg || axis.neutral_deg > axis.max_deg ||
            axis.max_speed_deg_s <= 0.0 || axis.smoothing_tau_s < 0.0) {
            throw std::invalid_argument("invalid limits, neutral, speed or filter: " + axis.axis_id);
        }
        // Keep subsequent double-precision sums/differences representable.
        if (!std::isfinite(axis.max_deg - axis.min_deg) ||
            !std::isfinite(std::abs(axis.neutral_deg) +
                           std::abs(axis.gain_x_deg) + std::abs(axis.gain_y_deg))) {
            throw std::invalid_argument("calibration arithmetic would overflow: " + axis.axis_id);
        }
    }
}

const char* input_state_name(InputState state) {
    switch (state) {
        case InputState::NoInput: return "no_input";
        case InputState::TrackingOrHolding: return "tracking_or_holding";
        case InputState::ReturningToNeutral: return "returning_to_neutral";
        case InputState::CommandHeld: return "command_held";
    }
    return "unknown";
}

MotionMapper::MotionMapper(std::vector<AxisCalibration> axes,
                           const std::vector<double>& initial_commands_deg,
                           MapperOptions options,
                           double start_time_s)
    : axes_(std::move(axes)), commands_deg_(initial_commands_deg), options_(options),
      last_step_s_(start_time_s), last_event_s_(start_time_s) {
    validate_calibrations(axes_);
    if (!std::isfinite(start_time_s) || start_time_s < 0.0 ||
        !std::isfinite(options_.input_hold_s) || options_.input_hold_s < 0.0 ||
        !std::isfinite(options_.max_step_s) || options_.max_step_s <= 0.0) {
        throw std::invalid_argument("invalid mapper time/options");
    }
    if (commands_deg_.size() != axes_.size()) {
        throw std::invalid_argument("one initial command is required per configured axis");
    }
    for (std::size_t i = 0; i < axes_.size(); ++i) {
        if (!std::isfinite(commands_deg_[i]) || commands_deg_[i] < axes_[i].min_deg ||
            commands_deg_[i] > axes_[i].max_deg) {
            throw std::invalid_argument("initial command outside axis limits: " + axes_[i].axis_id);
        }
        if (!std::isfinite(axes_[i].max_speed_deg_s * options_.max_step_s)) {
            throw std::invalid_argument("speed/time product would overflow: " + axes_[i].axis_id);
        }
    }
}

void MotionMapper::check_event_time(double now_s) const {
    if (!std::isfinite(now_s) || now_s < last_event_s_) {
        throw std::invalid_argument("timestamps must be finite and monotonic on one local clock");
    }
}

std::size_t MotionMapper::submit_pose(const ShadowPose& pose, double arrival_time_s) {
    check_event_time(arrival_time_s);
    std::size_t accepted = 0;
    for (std::size_t i = 0; i < kRodCount; ++i) {
        const auto& input = pose.rods[i];
        if (!input.valid || !std::isfinite(input.x) || !std::isfinite(input.y)) continue;
        auto& last = last_rods_[i];
        last.x = std::clamp(input.x, -1.0, 1.0);
        last.y = std::clamp(input.y, -1.0, 1.0);
        last.clamped = (last.x != input.x || last.y != input.y);
        last.last_good_s = arrival_time_s;
        last.available = true;
        ++accepted;
    }
    last_event_s_ = arrival_time_s;
    return accepted;
}

void MotionMapper::clear_inputs(double now_s) {
    check_event_time(now_s);
    last_rods_ = {};
    last_event_s_ = now_s;
}

std::vector<AxisOutput> MotionMapper::hold(double now_s) {
    check_event_time(now_s);
    std::vector<AxisOutput> output;
    output.reserve(axes_.size());
    for (std::size_t i = 0; i < axes_.size(); ++i) {
        AxisOutput item;
        item.axis_id = axes_[i].axis_id;
        item.rod = axes_[i].rod;
        item.angle_deg = commands_deg_[i];
        item.limited_target_deg = commands_deg_[i];
        item.input_state = InputState::CommandHeld;
        output.push_back(item);
    }
    last_step_s_ = now_s;
    last_event_s_ = now_s;
    return output;
}

std::vector<AxisOutput> MotionMapper::step(double now_s) {
    check_event_time(now_s);
    const double dt = std::min(now_s - last_step_s_, options_.max_step_s);
    std::vector<AxisOutput> output;
    output.reserve(axes_.size());

    for (std::size_t i = 0; i < axes_.size(); ++i) {
        const auto& axis = axes_[i];
        const auto& last = last_rods_[rod_index(axis.rod)];
        AxisOutput result;
        result.axis_id = axis.axis_id;
        result.rod = axis.rod;
        double raw_target = axis.neutral_deg;
        if (last.available) {
            if (now_s - last.last_good_s <= options_.input_hold_s) {
                result.input_state = InputState::TrackingOrHolding;
                raw_target += axis.gain_x_deg * last.x + axis.gain_y_deg * last.y;
                result.input_clamped = last.clamped;
            } else {
                result.input_state = InputState::ReturningToNeutral;
            }
        }
        result.limited_target_deg = std::clamp(raw_target, axis.min_deg, axis.max_deg);
        result.angle_limited = (result.limited_target_deg != raw_target);

        // Filter from the last emitted command. Keeping no separate filter
        // accumulator avoids windup and continued outward motion after timeout.
        double alpha = 0.0;
        if (dt > 0.0) {
            alpha = axis.smoothing_tau_s == 0.0
                        ? 1.0 : -std::expm1(-dt / axis.smoothing_tau_s);
        }
        const double requested_delta = alpha * (result.limited_target_deg - commands_deg_[i]);
        const double max_delta = axis.max_speed_deg_s * dt;
        const double delta = std::clamp(requested_delta, -max_delta, max_delta);
        result.speed_limited = (delta != requested_delta);
        result.angle_deg = std::clamp(commands_deg_[i] + delta, axis.min_deg, axis.max_deg);
        output.push_back(result);
    }

    // Only commit state after producing a complete output vector.
    for (std::size_t i = 0; i < output.size(); ++i) commands_deg_[i] = output[i].angle_deg;
    last_step_s_ = now_s;
    last_event_s_ = now_s;
    return output;
}

}  // namespace shadow
