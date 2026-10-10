#include "shadow/controller.hpp"

#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <utility>

namespace shadow {
const char* show_mode_name(ShowMode mode) {
    switch (mode) {
        case ShowMode::Stopped: return "stopped";
        case ShowMode::Script: return "script";
        case ShowMode::Touch: return "touch";
        case ShowMode::Camera: return "camera";
    }
    throw std::invalid_argument("invalid show mode");
}
ShowMode parse_show_mode(const std::string& mode) {
    if (mode == "stopped" || mode == "stop") return ShowMode::Stopped;
    if (mode == "script") return ShowMode::Script;
    if (mode == "touch") return ShowMode::Touch;
    if (mode == "camera") return ShowMode::Camera;
    throw std::invalid_argument("unknown mode: " + mode);
}

ShowController::ShowController(Script script, std::vector<AxisCalibration> axes,
                               const std::vector<double>& initial_commands,
                               std::unique_ptr<AudioPlayer> audio,
                               RetargetConfig retarget, MapperOptions mapper,
                               double start_time_s)
    : script_(std::move(script)), mapper_(std::move(axes), initial_commands, mapper, start_time_s),
      retargeter_(retarget), audio_(std::move(audio)), last_event_s_(start_time_s) {
    if (!audio_) throw std::invalid_argument("audio clock/backend is required");
    if (script_.frames.empty() || !std::isfinite(script_.duration_s) || script_.duration_s <= 0.0) {
        throw std::invalid_argument("a validated nonempty script is required");
    }
}
void ShowController::check_time(double now_s) const {
    if (!std::isfinite(now_s) || now_s < last_event_s_) {
        throw std::invalid_argument("controller times must be finite and monotonic");
    }
}
void ShowController::set_mode(ShowMode mode, double now_s) {
    check_time(now_s);
    show_mode_name(mode);
    audio_->stop(now_s);
    mapper_.clear_inputs(now_s);
    mode_ = ShowMode::Stopped;
    paused_ = false;
    playback_s_ = 0.0;
    last_event_s_ = now_s;
    if (mode == ShowMode::Script) audio_->start(now_s);
    mode_ = mode;
}
void ShowController::pause(double now_s) {
    check_time(now_s);
    if (mode_ != ShowMode::Script || paused_) {
        throw std::logic_error("pause requires a running script");
    }
    audio_->pause(now_s);
    playback_s_ = audio_->position_s(now_s);
    mapper_.clear_inputs(now_s);
    paused_ = true;
    last_event_s_ = now_s;
}
void ShowController::resume(double now_s) {
    check_time(now_s);
    if (mode_ != ShowMode::Script || !paused_) {
        throw std::logic_error("resume requires a paused script");
    }
    audio_->resume(now_s);
    paused_ = false;
    last_event_s_ = now_s;
}
void ShowController::restart(double now_s) { set_mode(ShowMode::Script, now_s); }
void ShowController::reset_input_sequences(double now_s) {
    check_time(now_s);
    if (mode_ != ShowMode::Stopped) {
        throw std::logic_error("stop before resetting producer sequence counters");
    }
    sequence_seen_ = {};
    last_sequence_ = {};
    input_version_ = {};
    input_session_ = {};
    last_track_ = {};
    input_reset_required_ = {};
    mapper_.clear_inputs(now_s);
    last_event_s_ = now_s;
}
ReceiveResult ShowController::receive(const InputFrame& frame, double arrival_s) {
    check_time(arrival_s);
    if (frame.source != InputSource::Touch && frame.source != InputSource::Camera) {
        throw std::invalid_argument("unknown input source");
    }
    const std::size_t slot = frame.source == InputSource::Touch ? 0 : 1;
    // Validate before changing lifecycle state or consuming a sequence number.
    (void)serialize_input_frame(frame);
    const bool active = (mode_ == ShowMode::Touch && frame.source == InputSource::Touch) ||
                        (mode_ == ShowMode::Camera && frame.source == InputSource::Camera);
    if (input_reset_required_[slot] || (sequence_seen_[slot] &&
        (input_version_[slot] != frame.version ||
         (frame.version == 2 && input_session_[slot] != frame.session_id)))) {
        // Pin the original session until an explicit stopped reset. Otherwise a
        // delayed packet from a previous process could switch the session back.
        input_reset_required_[slot] = true;
        if (active) set_mode(ShowMode::Stopped, arrival_s);
        last_event_s_ = arrival_s;
        return ReceiveResult::InputResetRequired;
    }
    if (sequence_seen_[slot] && frame.seq <= last_sequence_[slot]) {
        last_event_s_ = arrival_s;
        return ReceiveResult::DuplicateOrOld;
    }
    if (frame.version == 2 && frame.track_id != 0 && last_track_[slot] != 0 &&
        frame.track_id < last_track_[slot]) {
        last_event_s_ = arrival_s;
        return ReceiveResult::DuplicateOrOld;
    }
    const auto pose = retargeter_.map(frame);
    const bool changed_person = frame.version == 2 && frame.detected &&
        last_track_[slot] != 0 && frame.track_id != last_track_[slot];
    sequence_seen_[slot] = true;
    last_sequence_[slot] = frame.seq;
    input_version_[slot] = frame.version;
    input_session_[slot] = frame.session_id;
    if (frame.version == 2 && frame.detected) last_track_[slot] = frame.track_id;
    last_event_s_ = arrival_s;
    if (!active) return ReceiveResult::InactiveSource;
    if (changed_person) {
        set_mode(ShowMode::Stopped, arrival_s);
        return ReceiveResult::TrackingChanged;
    }
    mapper_.submit_pose(pose, arrival_s);
    return ReceiveResult::Accepted;
}
ControlTick ShowController::tick(double now_s) {
    check_time(now_s);
    if (mode_ == ShowMode::Script && !paused_) {
        playback_s_ = audio_->position_s(now_s);
        if (!std::isfinite(playback_s_) || playback_s_ < 0.0) {
            throw std::runtime_error("audio backend returned an invalid position");
        }
        playback_s_ = std::min(playback_s_, script_.duration_s);
        if (playback_s_ >= script_.duration_s || audio_->ended(now_s)) {
            // Completion has the same safe-neutral policy as an explicit stop.
            audio_->stop(now_s);
            mapper_.clear_inputs(now_s);
            mode_ = ShowMode::Stopped;
        } else {
            mapper_.submit_pose(script_.sample(playback_s_), now_s);
        }
    }
    auto outputs = paused_ ? mapper_.hold(now_s) : mapper_.step(now_s);
    last_event_s_ = now_s;
    return {now_s, mode_, paused_, playback_s_, std::move(outputs)};
}
} // namespace shadow
