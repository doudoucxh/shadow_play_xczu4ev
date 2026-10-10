#pragma once

#include "shadow/motion_mapper.hpp"

#include <cstdint>
#include <map>
#include <string>
#include <vector>

namespace shadow {

enum class InputSource { Touch, Camera };
const char* input_source_name(InputSource source);

struct Landmark {
    double x = 0.0;
    double y = 0.0;
    double confidence = 0.0;
    bool valid = false;
};

struct InputFrame {
    InputSource source = InputSource::Touch;
    std::uint64_t seq = 0;
    std::map<std::string, Landmark> points;
    std::uint64_t version = 1;
    std::string session_id;
    std::uint64_t track_id = 0;
    // Sender monotonic time, for diagnostics only. Receiver time owns timeouts.
    double captured_s = 0.0;
    bool detected = false;
};

// Normalized protocol v1, or camera-only v2 with session/tracking metadata.
// Throws std::invalid_argument for malformed input.
// A missing point, or a point with valid:false, is unavailable.
InputFrame parse_input_frame(const std::string& json_line);
std::string serialize_input_frame(const InputFrame& frame);

struct RecordedInput {
    double arrival_s = 0.0;
    InputFrame frame;
};

// JSONL records: {"arrival_ms":0,"frame":{...protocol frame...}}.
// Times are receiver-relative and nondecreasing. Sequence numbers are retained;
// the controller owns sequence filtering and source selection.
std::vector<RecordedInput> load_input_replay(const std::string& path);

struct RetargetConfig {
    double confidence_threshold = 0.5;
    double min_shoulder_width = 0.05;
    double hand_span_shoulders = 2.0;
    double neck_gain_x = 2.0;
    double neck_gain_y = 2.0;
    // Calibrate the resting neck, estimated from the shoulder midpoint if absent.
    double neck_origin_x = 0.5;
    double neck_origin_y = 0.5;
    bool mirror_x = false;
};

// Stateless skeleton-to-rod prototype. No device I/O, timing, or hidden filter.
// Output x is screen-right and y is up; names remain anatomical left/right.
// The shared MotionMapper handles timeouts, output smoothing and angle limits.
class Retargeter {
public:
    explicit Retargeter(RetargetConfig config = {});
    ShadowPose map(const InputFrame& frame) const;

private:
    RetargetConfig config_;
};

}  // namespace shadow
