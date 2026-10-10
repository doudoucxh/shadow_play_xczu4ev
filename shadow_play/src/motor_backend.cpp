#include "shadow/motor_backend.hpp"
#include <nlohmann/json.hpp>
#include <cmath>
#include <iomanip>
#include <limits>
#include <set>
#include <stdexcept>
#include <utility>

namespace shadow {
CsvMotorBackend::CsvMotorBackend(std::ostream& stream) : stream_(stream) {
    stream_ << "time_s,mode,playback_s,axis_id,rod,angle_deg,limited_target_deg,input_state,"
               "input_clamped,angle_limited,speed_limited\n";
    if (!stream_) throw std::runtime_error("cannot write trace header");
}
void CsvMotorBackend::send(const ControlTick& tick) {
    if (!std::isfinite(tick.time_s) || !std::isfinite(tick.playback_s)) {
        throw std::invalid_argument("invalid trace timestamp");
    }
    stream_ << std::fixed << std::setprecision(6);
    for (const auto& axis : tick.axes) {
        stream_ << tick.time_s << ',' << (tick.paused ? "paused" : show_mode_name(tick.mode))
                << ',' << tick.playback_s << ',' << axis.axis_id << ',' << rod_name(axis.rod)
                << ',' << axis.angle_deg << ',' << axis.limited_target_deg << ','
                << input_state_name(axis.input_state) << ',' << axis.input_clamped << ','
                << axis.angle_limited << ',' << axis.speed_limited << '\n';
    }
    if (!stream_) throw std::runtime_error("failed writing motor trace");
}
void CsvMotorBackend::shutdown() {
    stream_.flush();
    if (!stream_) throw std::runtime_error("failed flushing motor trace");
}

std::string serialize_motor_frame(const ControlTick& tick, std::uint64_t seq) {
    if (!std::isfinite(tick.time_s) || tick.time_s < 0.0 ||
        !std::isfinite(tick.playback_s) || tick.playback_s < 0.0) {
        throw std::invalid_argument("motor frame times must be finite and nonnegative");
    }
    const std::string mode = show_mode_name(tick.mode); // Validates enum.
    if (tick.axes.empty()) throw std::invalid_argument("motor frame requires at least one axis");
    nlohmann::json axes = nlohmann::json::array();
    std::set<std::string> ids;
    for (const auto& axis : tick.axes) {
        if (axis.axis_id.empty()) throw std::invalid_argument("empty motor axis ID");
        for (const char c : axis.axis_id) {
            if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
                  (c >= '0' && c <= '9') || c == '_' || c == '-')) {
                throw std::invalid_argument("invalid motor axis ID: " + axis.axis_id);
            }
        }
        if (!ids.insert(axis.axis_id).second) {
            throw std::invalid_argument("duplicate motor axis ID: " + axis.axis_id);
        }
        if (!std::isfinite(axis.angle_deg)) {
            throw std::invalid_argument("non-finite motor angle: " + axis.axis_id);
        }
        const std::string rod = rod_name(axis.rod); // Validates enum.
        switch (axis.input_state) {
            case InputState::NoInput:
            case InputState::TrackingOrHolding:
            case InputState::ReturningToNeutral:
            case InputState::CommandHeld:
                break;
            default:
                throw std::invalid_argument("invalid motor input state: " + axis.axis_id);
        }
        axes.push_back({{"axis_id", axis.axis_id}, {"rod", rod},
                        {"angle_deg", axis.angle_deg},
                        {"input_state", input_state_name(axis.input_state)},
                        {"input_clamped", axis.input_clamped},
                        {"angle_limited", axis.angle_limited},
                        {"speed_limited", axis.speed_limited}});
    }
    return nlohmann::json{{"version", 1}, {"type", "motor_targets"}, {"seq", seq},
                          {"time_s", tick.time_s}, {"mode", mode},
                          {"paused", tick.paused}, {"playback_s", tick.playback_s},
                          {"axes", std::move(axes)}}.dump();
}

JsonlMotorBackend::JsonlMotorBackend(std::ostream& stream) : stream_(stream) {
    if (!stream_) throw std::runtime_error("cannot write motor JSONL");
}
void JsonlMotorBackend::send(const ControlTick& tick) {
    if (sequence_exhausted_) throw std::overflow_error("motor sequence exhausted");
    // Validate/serialize all axes before writing. Never emit half a frame due
    // to a malformed late axis; physical I/O failure can still truncate a line.
    const auto line = serialize_motor_frame(tick, next_sequence_);
    stream_ << line << '\n';
    stream_.flush();
    if (!stream_) throw std::runtime_error("failed writing or flushing motor JSONL");
    if (next_sequence_ == std::numeric_limits<std::uint64_t>::max()) {
        sequence_exhausted_ = true;
    } else {
        ++next_sequence_;
    }
}
void JsonlMotorBackend::shutdown() {
    stream_.flush();
    if (!stream_) throw std::runtime_error("failed flushing motor JSONL");
}
} // namespace shadow
