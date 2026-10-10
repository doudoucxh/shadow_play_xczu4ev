#include "shadow/audio.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <fstream>
#include <limits>
#include <stdexcept>
#include <vector>

#ifdef SHADOW_HAVE_ALSA
#include <alsa/asoundlib.h>
#endif

namespace shadow {
namespace {

struct WaveData {
    WavInfo info;
    std::uint64_t offset = 0;
    std::uint64_t bytes = 0;
    std::uint16_t alignment = 0;
};

std::uint16_t u16(const unsigned char* data) {
    return static_cast<std::uint16_t>(data[0] | (static_cast<unsigned>(data[1]) << 8));
}

std::uint32_t u32(const unsigned char* data) {
    return static_cast<std::uint32_t>(data[0]) |
        (static_cast<std::uint32_t>(data[1]) << 8) |
        (static_cast<std::uint32_t>(data[2]) << 16) |
        (static_cast<std::uint32_t>(data[3]) << 24);
}

void read_exact(std::ifstream& file, unsigned char* out, std::size_t count) {
    if (!file.read(reinterpret_cast<char*>(out), static_cast<std::streamsize>(count))) {
        throw std::runtime_error("truncated WAV data");
    }
}

WaveData read_wave(const std::string& path) {
    try {
        std::ifstream file(path, std::ios::binary | std::ios::ate);
        if (!file) throw std::runtime_error("cannot open file");
        const auto end = file.tellg();
        if (end < 12) throw std::runtime_error("file is too short for RIFF/WAVE");
        const auto size = static_cast<std::uint64_t>(end);
        file.seekg(0);
        std::array<unsigned char, 12> header{};
        read_exact(file, header.data(), header.size());
        if (std::string(reinterpret_cast<char*>(header.data()), 4) != "RIFF" ||
            std::string(reinterpret_cast<char*>(header.data() + 8), 4) != "WAVE") {
            throw std::runtime_error("expected little-endian RIFF/WAVE");
        }
        const std::uint64_t riff_end = static_cast<std::uint64_t>(u32(header.data() + 4)) + 8;
        if (riff_end < 12 || riff_end != size) {
            throw std::runtime_error("RIFF size does not match the file size");
        }
        WaveData result;
        bool have_format = false;
        bool have_data = false;
        std::uint64_t offset = 12;
        while (offset < riff_end) {
            if (riff_end - offset < 8) throw std::runtime_error("incomplete WAV chunk header");
            file.seekg(static_cast<std::streamoff>(offset));
            std::array<unsigned char, 8> chunk{};
            read_exact(file, chunk.data(), chunk.size());
            const std::string id(reinterpret_cast<char*>(chunk.data()), 4);
            const std::uint64_t bytes = u32(chunk.data() + 4);
            const std::uint64_t chunk_end = offset + 8 + bytes + (bytes & 1U);
            if (chunk_end > riff_end) throw std::runtime_error("WAV chunk exceeds file size");
            if (id == "fmt ") {
                if (have_format || bytes < 16) throw std::runtime_error("invalid/duplicate WAV format");
                std::array<unsigned char, 16> format{};
                read_exact(file, format.data(), format.size());
                if (u16(format.data()) != 1) {
                    throw std::runtime_error("only uncompressed integer PCM WAV is supported");
                }
                result.info.channels = u16(format.data() + 2);
                result.info.sample_rate = u32(format.data() + 4);
                result.info.bits_per_sample = u16(format.data() + 14);
                result.alignment = u16(format.data() + 12);
                const auto bits = result.info.bits_per_sample;
                if (result.info.channels == 0 || result.info.channels > 8 ||
                    result.info.sample_rate == 0 ||
                    (bits != 8 && bits != 16 && bits != 24 && bits != 32)) {
                    throw std::runtime_error("unsupported PCM channels/rate/sample width");
                }
                const auto expected_alignment = result.info.channels * (bits / 8);
                if (result.alignment != expected_alignment ||
                    static_cast<std::uint64_t>(u32(format.data() + 8)) !=
                    static_cast<std::uint64_t>(result.info.sample_rate) * result.alignment) {
                    throw std::runtime_error("inconsistent PCM block alignment or byte rate");
                }
                have_format = true;
            } else if (id == "data") {
                if (have_data || bytes == 0) throw std::runtime_error("empty/duplicate WAV data");
                result.offset = offset + 8;
                result.bytes = bytes;
                have_data = true;
            }
            offset = chunk_end;
        }
        if (!have_format || !have_data || result.bytes % result.alignment != 0) {
            throw std::runtime_error("WAV needs a format and complete PCM sample frames");
        }
        result.info.frame_count = result.bytes / result.alignment;
        result.info.duration_s = static_cast<double>(result.info.frame_count) / result.info.sample_rate;
        return result;
    } catch (const std::exception& error) {
        throw std::runtime_error("WAV '" + path + "': " + error.what());
    }
}

class EventClock {
public:
    void check(double now) {
        if (!std::isfinite(now) || now < 0.0 || now < previous_) {
            throw std::invalid_argument("audio time must be finite, nonnegative and monotonic");
        }
        previous_ = now;
    }
private:
    double previous_ = 0.0;
};

enum class PlayerState { Stopped, Playing, Paused, Finished };

class ClockAudio final : public AudioPlayer {
public:
    explicit ClockAudio(double duration) : duration_(duration) {
        if (!std::isfinite(duration) || duration <= 0.0) {
            throw std::invalid_argument("audio duration must be finite and positive");
        }
    }
    void start(double now) override {
        clock_.check(now);
        position_ = 0.0;
        anchor_ = now;
        state_ = PlayerState::Playing;
    }
    void pause(double now) override {
        update(now);
        if (state_ == PlayerState::Playing) state_ = PlayerState::Paused;
    }
    void resume(double now) override {
        update(now);
        if (state_ == PlayerState::Stopped) throw std::logic_error("start audio before resuming");
        if (state_ == PlayerState::Paused) {
            anchor_ = now;
            state_ = PlayerState::Playing;
        }
    }
    void stop(double now) override {
        clock_.check(now);
        state_ = PlayerState::Stopped;
        position_ = 0.0;
    }
    double position_s(double now) override { update(now); return position_; }
    bool ended(double now) override { update(now); return state_ == PlayerState::Finished; }
private:
    void update(double now) {
        clock_.check(now);
        if (state_ == PlayerState::Playing) {
            position_ = std::min(duration_, position_ + now - anchor_);
            anchor_ = now;
            if (position_ >= duration_) state_ = PlayerState::Finished;
        }
    }
    EventClock clock_;
    PlayerState state_ = PlayerState::Stopped;
    double duration_;
    double position_ = 0.0;
    double anchor_ = 0.0;
};

#ifdef SHADOW_HAVE_ALSA

class AlsaAudio final : public AudioPlayer {
public:
    AlsaAudio(const std::string& path, const std::string& device) : wave_(read_wave(path)) {
        if (wave_.info.bits_per_sample != 16 || wave_.info.channels > 2) {
            throw std::runtime_error("ALSA playback requires PCM16 mono/stereo WAV");
        }
        if (wave_.bytes > 512U * 1024U * 1024U) {
            throw std::runtime_error("WAV exceeds 512 MiB in-memory playback limit");
        }
        samples_.resize(static_cast<std::size_t>(wave_.bytes));
        std::ifstream file(path, std::ios::binary);
        file.seekg(static_cast<std::streamoff>(wave_.offset));
        read_exact(file, samples_.data(), samples_.size());
        check(snd_pcm_open(&pcm_, device.c_str(), SND_PCM_STREAM_PLAYBACK, SND_PCM_NONBLOCK),
              "open ALSA device " + device);
        try {
            check(snd_pcm_set_params(pcm_, SND_PCM_FORMAT_S16_LE, SND_PCM_ACCESS_RW_INTERLEAVED,
                                    wave_.info.channels, wave_.info.sample_rate, 0, 250000),
                  "configure PCM16 playback");
            snd_pcm_uframes_t period = 0;
            check(snd_pcm_get_params(pcm_, &buffer_frames_, &period), "get ALSA buffer size");
            snd_pcm_sw_params_t* software = nullptr;
            snd_pcm_sw_params_alloca(&software);
            check(snd_pcm_sw_params_current(pcm_, software), "get ALSA software params");
            snd_pcm_uframes_t boundary = 0;
            check(snd_pcm_sw_params_get_boundary(software, &boundary), "get ALSA boundary");
            check(snd_pcm_sw_params_set_start_threshold(pcm_, software, boundary),
                  "configure explicit ALSA start");
            check(snd_pcm_sw_params(pcm_, software), "apply ALSA software params");
        } catch (...) {
            snd_pcm_close(pcm_);
            pcm_ = nullptr;
            throw;
        }
    }
    ~AlsaAudio() override { if (pcm_) snd_pcm_close(pcm_); }
    void start(double now) override {
        clock_.check(now);
        check(snd_pcm_drop(pcm_), "reset ALSA playback");
        check(snd_pcm_prepare(pcm_), "prepare ALSA playback");
        written_ = 0;
        played_ = 0;
        have_serviced_ = false;
        state_ = PlayerState::Stopped;
        fill();
        check(snd_pcm_start(pcm_), "start ALSA playback");
        state_ = PlayerState::Playing;
    }
    void pause(double now) override {
        service(now);
        if (state_ == PlayerState::Playing) {
            check(snd_pcm_pause(pcm_, 1), "pause ALSA device (lossless pause support required)");
            state_ = PlayerState::Paused;
        }
    }
    void resume(double now) override {
        service(now);
        if (state_ == PlayerState::Stopped) throw std::logic_error("start audio before resuming");
        if (state_ == PlayerState::Paused) {
            check(snd_pcm_pause(pcm_, 0), "resume ALSA device");
            state_ = PlayerState::Playing;
        }
    }
    void stop(double now) override {
        clock_.check(now);
        check(snd_pcm_drop(pcm_), "stop ALSA playback");
        state_ = PlayerState::Stopped;
        written_ = 0;
        played_ = 0;
        have_serviced_ = false;
    }
    double position_s(double now) override {
        service(now);
        return static_cast<double>(played_) / wave_.info.sample_rate;
    }
    bool ended(double now) override { service(now); return state_ == PlayerState::Finished; }
private:
    static void check(int result, const std::string& action) {
        if (result < 0) throw std::runtime_error(action + ": " + snd_strerror(result));
    }
    void finish() {
        played_ = wave_.info.frame_count;
        check(snd_pcm_drop(pcm_), "finish ALSA playback");
        state_ = PlayerState::Finished;
    }
    void fill() {
        // Bounded work per tick: at most one device buffer. A short file can fit
        // entirely; a null test sink therefore cannot consume 90 s in one call.
        std::uint64_t budget = buffer_frames_;
        while (written_ < wave_.info.frame_count && budget > 0) {
            const auto count = static_cast<snd_pcm_uframes_t>(
                std::min(wave_.info.frame_count - written_, budget));
            const auto result = snd_pcm_writei(pcm_,
                samples_.data() + static_cast<std::size_t>(written_ * wave_.alignment), count);
            if (result == -EAGAIN || result == 0) return;
            if (result < 0) {
                throw std::runtime_error(std::string("ALSA write failed; playback stopped to avoid drift: ") +
                                         snd_strerror(static_cast<int>(result)));
            }
            written_ += static_cast<std::uint64_t>(result);
            budget -= static_cast<std::uint64_t>(result);
        }
    }
    void service(double now) {
        clock_.check(now);
        if (have_serviced_ && now == last_service_s_) return;
        have_serviced_ = true;
        last_service_s_ = now;
        if (state_ != PlayerState::Playing) return;
        try {
            service_device();
        } catch (...) {
            // A failed refill must stop sound as well as reporting the error.
            snd_pcm_drop(pcm_);
            state_ = PlayerState::Stopped;
            throw;
        }
    }
    void service_device() {
        const auto device_state = snd_pcm_state(pcm_);
        if (device_state == SND_PCM_STATE_XRUN) {
            // Once every sample has been queued, running out of samples is the
            // expected end. Any earlier underrun is an explicit timing failure.
            if (written_ == wave_.info.frame_count) { finish(); return; }
            throw std::runtime_error("ALSA underrun: control loop missed audio refill; playback aborted");
        }
        if (device_state != SND_PCM_STATE_RUNNING) {
            throw std::runtime_error("ALSA playback left RUNNING state; playback aborted");
        }
        snd_pcm_sframes_t delay = 0;
        const int result = snd_pcm_delay(pcm_, &delay);
        if (result == -EPIPE && written_ == wave_.info.frame_count) { finish(); return; }
        check(result, "read ALSA played-sample position");
        const auto queued = static_cast<std::uint64_t>(std::max<snd_pcm_sframes_t>(0, delay));
        const auto estimate = queued <= written_ ? written_ - queued : 0;
        played_ = std::max(played_, std::min(estimate, wave_.info.frame_count));
        if (played_ == wave_.info.frame_count) { finish(); return; }
        fill();
    }
    WaveData wave_;
    std::vector<unsigned char> samples_;
    snd_pcm_t* pcm_ = nullptr;
    snd_pcm_uframes_t buffer_frames_ = 0;
    std::uint64_t written_ = 0;
    std::uint64_t played_ = 0;
    EventClock clock_;
    PlayerState state_ = PlayerState::Stopped;
    bool have_serviced_ = false;
    double last_service_s_ = 0.0;
};
#endif

}  // namespace

WavInfo inspect_wav(const std::string& path) { return read_wave(path).info; }

std::unique_ptr<AudioPlayer> make_clock_audio(double duration_s) {
    return std::make_unique<ClockAudio>(duration_s);
}

std::unique_ptr<AudioPlayer> make_wav_audio(const std::string& path, const std::string& device) {
#ifdef SHADOW_HAVE_ALSA
    return std::make_unique<AlsaAudio>(path, device);
#else
    (void)path;
    (void)device;
    throw std::runtime_error("WAV device playback unavailable: rebuild on Linux with ALSA development files; "
                             "use clock audio for simulation");
#endif
}

}  // namespace shadow
