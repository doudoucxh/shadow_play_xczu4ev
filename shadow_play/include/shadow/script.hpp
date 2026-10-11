#pragma once

#include "shadow/motion_mapper.hpp"

#include <string>
#include <vector>

namespace shadow {

struct ScriptKeyframe {
    double time_s = 0.0;
    ShadowPose pose;
};

struct Script {
    enum class Interpolation { Linear, Quintic };
    double duration_s = 0.0;
    Interpolation interpolation = Interpolation::Linear;
    // Absolute/normalized path resolved against the script's directory, or empty.
    std::string audio_file;
    std::vector<ScriptKeyframe> frames;

    // Clamp finite times to [0, duration_s]; interpolate normalized rod targets.
    // Scripts returned by load_script_json() always have valid, complete poses.
    ShadowPose sample(double time_s) const;
};

// Schema v1: duration_ms, optional audio_file/interpolation, frames[{time_ms, rods:{...}}].
// interpolation is "linear" (default) or "quintic" (zero velocity/acceleration
// at each keyframe). These are target trajectories, not motor feedback.
// Every frame contains all five named rods as [x,y], both finite in [-1,1].
// Times strictly increase from 0 to duration_ms. Throws on malformed input.
Script load_script_json(const std::string& path);

}  // namespace shadow
