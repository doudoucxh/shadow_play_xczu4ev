#pragma once

#include <cstdint>
#include <memory>
#include <string>

namespace shadow {

struct WavInfo {
    double duration_s = 0.0;
    std::uint32_t sample_rate = 0;
    std::uint16_t channels = 0;
    std::uint16_t bits_per_sample = 0;
    // A frame contains one sample for each channel.
    std::uint64_t frame_count = 0;
};

// Validates RIFF/WAVE uncompressed integer PCM (8/16/24/32 bit).
WavInfo inspect_wav(const std::string& path);

// All calls must use one local monotonic clock and one control thread.
// position_s()/ended() must be polled at the control cadence (e.g. 20 ms).
// Device audio uses actually played samples, not wall time, as its position.
class AudioPlayer {
public:
    virtual ~AudioPlayer() = default;
    virtual void start(double now_s) = 0;  // Always restart from the beginning.
    virtual void pause(double now_s) = 0;
    virtual void resume(double now_s) = 0;
    virtual void stop(double now_s) = 0;
    virtual double position_s(double now_s) = 0;
    virtual bool ended(double now_s) = 0;
};

// No sound, deterministic clock for simulation and file replay.
std::unique_ptr<AudioPlayer> make_clock_audio(double duration_s);

// Linux ALSA backend, built only with SHADOW_HAVE_ALSA. Currently accepts PCM16
// mono/stereo. Throws a clear error when ALSA support/device is unavailable.
// A device that cannot pause losslessly reports an error instead of drifting.
std::unique_ptr<AudioPlayer> make_wav_audio(
    const std::string& path, const std::string& device = "default");

}  // namespace shadow
