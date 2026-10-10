#pragma once

#include "shadow/audio.hpp"
#include "shadow/input.hpp"
#include "shadow/motion_mapper.hpp"
#include "shadow/script.hpp"

#include <array>
#include <cstdint>
#include <memory>
#include <string>
#include <vector>

namespace shadow {

enum class ShowMode { Stopped, Script, Touch, Camera };
const char* show_mode_name(ShowMode mode);
ShowMode parse_show_mode(const std::string& mode);
enum class ReceiveResult {
    Accepted, InactiveSource, DuplicateOrOld,
    InputResetRequired,  // Producer session/protocol changed; stop/reset-inputs/rearm.
    TrackingChanged     // A new person was selected; stopped until explicit rearm.
};

struct ControlTick {
    double time_s = 0.0;
    ShowMode mode = ShowMode::Stopped;
    bool paused = false;
    double playback_s = 0.0;
    std::vector<AxisOutput> axes;
};

// One instance, one control thread. Input queues/network transport live outside.
class ShowController {
public:
    ShowController(Script script, std::vector<AxisCalibration> axes,
                   const std::vector<double>& initial_commands,
                   std::unique_ptr<AudioPlayer> audio,
                   RetargetConfig retarget = {}, MapperOptions mapper = {},
                   double start_time_s = 0.0);

    void set_mode(ShowMode mode, double now_s);
    void pause(double now_s);
    void resume(double now_s);
    void restart(double now_s);
    // Explicit producer restart: only allowed while stopped.
    void reset_input_sequences(double now_s);
    ReceiveResult receive(const InputFrame& frame, double arrival_s);
    ControlTick tick(double now_s);

    ShowMode mode() const noexcept { return mode_; }
    bool paused() const noexcept { return paused_; }

private:
    void check_time(double now_s) const;
    Script script_;
    MotionMapper mapper_;
    Retargeter retargeter_;
    std::unique_ptr<AudioPlayer> audio_;
    ShowMode mode_ = ShowMode::Stopped;
    bool paused_ = false;
    double playback_s_ = 0.0;
    double last_event_s_ = 0.0;
    std::array<bool, 2> sequence_seen_{};
    std::array<std::uint64_t, 2> last_sequence_{};
    std::array<std::uint64_t, 2> input_version_{};
    std::array<std::string, 2> input_session_{};
    std::array<std::uint64_t, 2> last_track_{};
    std::array<bool, 2> input_reset_required_{};
};

} // namespace shadow
