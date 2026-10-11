#include "shadow/audio.hpp"
#include "shadow/script.hpp"

#include <nlohmann/json.hpp>

#include <chrono>
#include <cmath>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <functional>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

void require(bool condition, const std::string& message) {
    if (!condition) throw std::runtime_error(message);
}

void near(double actual, double expected, const std::string& message) {
    require(std::abs(actual - expected) < 1e-9, message);
}

template<class Function> void rejects(Function action, const std::string& message) {
    bool threw = false;
    try { action(); } catch (const std::exception&) { threw = true; }
    require(threw, message);
}

class TemporaryFiles {
public:
    TemporaryFiles() {
        const auto tick = std::chrono::high_resolution_clock::now().time_since_epoch().count();
        for (int attempt = 0; attempt < 100; ++attempt) {
            directory_ = std::filesystem::current_path() /
                ("script_audio_test_" + std::to_string(tick) + "_" + std::to_string(attempt));
            if (std::filesystem::create_directory(directory_)) return;
        }
        throw std::runtime_error("could not allocate temporary test directory");
    }
    ~TemporaryFiles() {
        // Only individual known files in the directory this test created are
        // removed. Do not recursively delete an externally supplied path.
        std::error_code ignored;
        for (const auto& file : paths_) std::filesystem::remove(file, ignored);
        std::filesystem::remove(directory_, ignored);
    }
    std::string path(const std::string& name) {
        const auto file = directory_ / name;
        paths_.push_back(file);
        return file.string();
    }
private:
    std::filesystem::path directory_;
    std::vector<std::filesystem::path> paths_;
};

nlohmann::json valid_script() {
    auto point_frame = [](int time, double x, double y) {
        nlohmann::json rods = nlohmann::json::object();
        for (std::size_t i = 0; i < shadow::kRodCount; ++i) {
            rods[shadow::rod_name(static_cast<shadow::RodId>(i))] = {x, y};
        }
        return nlohmann::json{{"time_ms", time}, {"rods", rods}};
    };
    return {{"version", 1}, {"duration_ms", 2000}, {"audio_file", "cue.wav"},
            {"frames", {point_frame(0, -1.0, 0.0), point_frame(1000, 1.0, 0.4),
                        point_frame(2000, 0.0, -0.4)}}};
}

void write_json(const std::string& path, const nlohmann::json& document) {
    std::ofstream output(path);
    output << document.dump(2);
    if (!output) throw std::runtime_error("test JSON write failed");
}

void put16(std::ofstream& out, unsigned value) {
    out.put(static_cast<char>(value & 255U));
    out.put(static_cast<char>((value >> 8) & 255U));
}

void put32(std::ofstream& out, unsigned value) {
    put16(out, value & 65535U);
    put16(out, value >> 16);
}

void write_wav(const std::string& path, unsigned frames = 100) {
    // 100 mono PCM16 frames at 1 kHz, including an odd-sized metadata chunk.
    std::ofstream output(path, std::ios::binary);
    output.write("RIFF", 4);
    put32(output, 36 + frames * 2 + 10);
    output.write("WAVEJUNK", 8);
    put32(output, 1);
    output.put('x');
    output.put('\0');
    output.write("fmt ", 4);
    put32(output, 16);
    put16(output, 1);
    put16(output, 1);
    put32(output, 1000);
    put32(output, 2000);
    put16(output, 2);
    put16(output, 16);
    output.write("data", 4);
    put32(output, frames * 2);
    for (unsigned i = 0; i < frames; ++i) put16(output, 0);
    if (!output) throw std::runtime_error("test WAV write failed");
}

}  // namespace

int main() {
    TemporaryFiles temporary;
    int passed = 0;
    auto test = [&](const std::string& name, const std::function<void()>& action) {
        try {
            action();
            ++passed;
            std::cout << "PASS " << name << '\n';
        } catch (const std::exception& error) {
            std::cerr << "FAIL " << name << ": " << error.what() << '\n';
            throw;
        }
    };
    try {
        const auto script_path = temporary.path("script.json");
        test("script interpolation and endpoint clamping", [&] {
            write_json(script_path, valid_script());
            const auto script = shadow::load_script_json(script_path);
            near(script.duration_s, 2.0, "duration conversion");
            near(script.sample(0.5).rods[0].x, 0.0, "interpolation x");
            near(script.sample(0.5).rods[0].y, 0.2, "interpolation y");
            near(script.sample(1.5).rods[4].y, 0.0, "interpolation tiger");
            near(script.sample(-1.0).rods[0].x, -1.0, "negative time clamp");
            near(script.sample(999.0).rods[0].y, -0.4, "end clamp");
            require(script.sample(1.0).rods[0].valid, "valid flag");
            require(std::filesystem::path(script.audio_file) ==
                    std::filesystem::absolute(std::filesystem::path(script_path).parent_path() / "cue.wav"),
                    "relative audio resolution");
            rejects([&] { script.sample(std::numeric_limits<double>::quiet_NaN()); }, "reject NaN time");
        });
        test("script accepts absent audio", [&] {
            auto doc = valid_script(); doc.erase("audio_file"); write_json(script_path, doc);
            require(shadow::load_script_json(script_path).audio_file.empty(), "optional audio");
        });
        test("quintic interpolation preserves endpoints and eases each pose", [&] {
            auto doc = valid_script(); doc["interpolation"] = "quintic";
            write_json(script_path, doc);
            const auto script = shadow::load_script_json(script_path);
            near(script.sample(0.0).rods[0].x, -1.0, "start unchanged");
            near(script.sample(1.0).rods[0].x, 1.0, "keyframe unchanged");
            near(script.sample(2.0).rods[0].x, 0.0, "finish unchanged");
            near(script.sample(0.25).rods[0].x, -0.79296875, "quintic quarter point");
            near(script.sample(0.5).rods[0].x, 0.0, "quintic midpoint");
            const double h = 1e-4;
            const double left = script.sample(1.0-h).rods[0].x;
            const double center = script.sample(1.0).rods[0].x;
            const double right = script.sample(1.0+h).rods[0].x;
            require(std::abs((center-left)/h) < 1e-5, "left velocity near zero");
            require(std::abs((right-center)/h) < 1e-5, "right velocity near zero");
            require(std::abs((right-2*center+left)/(h*h)) < .004, "acceleration near zero");
            double prior = -1.0;
            for (int i = 0; i <= 1000; ++i) {
                const auto x = script.sample(i/1000.0).rods[0].x;
                require(x >= prior-1e-12 && x <= 1.0+1e-12, "no overshoot");
                prior = x;
            }
        });
        const std::vector<std::pair<std::string, std::function<void(nlohmann::json&)>>> bad_scripts = {
            {"unsupported version", [](auto& d) { d["version"] = 2; }},
            {"floating version", [](auto& d) { d["version"] = 1.0; }},
            {"unknown root field", [](auto& d) { d["duraton_ms"] = 2000; }},
            {"unknown interpolation", [](auto& d) { d["interpolation"] = "cubic"; }},
            {"non-string interpolation", [](auto& d) { d["interpolation"] = 1; }},
            {"unknown frame field", [](auto& d) { d["frames"][0]["time"] = 0; }},
            {"zero duration", [](auto& d) { d["duration_ms"] = 0; }},
            {"duplicate frame time", [](auto& d) { d["frames"][1]["time_ms"] = 0; }},
            {"start is not zero", [](auto& d) { d["frames"][0]["time_ms"] = 1; }},
            {"end is not duration", [](auto& d) { d["frames"][2]["time_ms"] = 1900; }},
            {"missing rod", [](auto& d) { d["frames"][0]["rods"].erase("tiger_tail"); }},
            {"unknown rod", [](auto& d) { d["frames"][0]["rods"]["tiger_ear"] = {0, 0}; }},
            {"coordinate outside range", [](auto& d) { d["frames"][0]["rods"]["tiger_tail"][0] = 2; }},
            {"missing coordinate", [](auto& d) { d["frames"][0]["rods"]["tiger_tail"] = {0}; }},
            {"string coordinate", [](auto& d) { d["frames"][0]["rods"]["tiger_tail"][0] = "0"; }},
            {"null coordinate", [](auto& d) { d["frames"][0]["rods"]["tiger_tail"][0] = nullptr; }}
        };
        for (const auto& entry : bad_scripts) {
            test("script rejects " + entry.first, [&] {
                auto doc = valid_script(); entry.second(doc); write_json(script_path, doc);
                rejects([&] { shadow::load_script_json(script_path); }, entry.first);
            });
        }
        test("script rejects trailing JSON", [&] {
            write_json(script_path, valid_script());
            { std::ofstream out(script_path, std::ios::app); out << " {}"; }
            rejects([&] { shadow::load_script_json(script_path); }, "trailing JSON");
        });
        test("script rejects duplicate keys", [&] {
            auto source = valid_script().dump();
            source.insert(1, "\"version\":1,");
            { std::ofstream out(script_path); out << source; }
            rejects([&] { shadow::load_script_json(script_path); }, "duplicate root key");
            source = valid_script().dump();
            const auto frame_pos = source.find("\"time_ms\":");
            source.insert(frame_pos, "\"time_ms\":0,");
            { std::ofstream out(script_path); out << source; }
            rejects([&] { shadow::load_script_json(script_path); }, "duplicate nested key");
        });
        test("clock pause resume stop restart", [&] {
            auto audio = shadow::make_clock_audio(2.0);
            near(audio->position_s(10), 0, "initial position");
            require(!audio->ended(10), "not initially ended");
            audio->start(10);
            near(audio->position_s(10.5), 0.5, "running position");
            audio->pause(10.75);
            near(audio->position_s(50), 0.75, "pause freezes position");
            audio->resume(50);
            near(audio->position_s(50.25), 1.0, "resume excludes paused time");
            require(audio->ended(60), "finishes at end");
            near(audio->position_s(60), 2.0, "clamps end");
            audio->start(60);
            near(audio->position_s(60.25), 0.25, "restart from zero");
            audio->stop(61);
            near(audio->position_s(62), 0.0, "stop resets position");
            require(!audio->ended(62), "stopped is not ended");
            rejects([&] { audio->resume(62); }, "stopped resume requires start");
        });
        test("clock rejects invalid or backwards time", [&] {
            rejects([] { shadow::make_clock_audio(0); }, "zero duration");
            rejects([] { shadow::make_clock_audio(std::numeric_limits<double>::infinity()); }, "infinite duration");
            auto audio = shadow::make_clock_audio(1);
            audio->start(20);
            rejects([&] { audio->pause(19); }, "backwards pause");
            rejects([&] { audio->position_s(std::numeric_limits<double>::quiet_NaN()); }, "NaN position");
            near(audio->position_s(20.5), 0.5, "invalid call did not mutate time");
        });
        const auto wav_path = temporary.path("test.wav");
        test("WAV parser handles PCM and padded metadata", [&] {
            write_wav(wav_path);
            const auto info = shadow::inspect_wav(wav_path);
            require(info.frame_count == 100 && info.channels == 1 &&
                    info.sample_rate == 1000 && info.bits_per_sample == 16, "PCM metadata");
            near(info.duration_s, 0.1, "WAV duration");
        });
        test("WAV rejects inconsistent format", [&] {
            write_wav(wav_path);
            { std::fstream file(wav_path, std::ios::in | std::ios::out | std::ios::binary);
              file.seekp(42); file.put('\4'); }  // block alignment must be 2.
            rejects([&] { shadow::inspect_wav(wav_path); }, "wrong block alignment");
        });
        test("WAV rejects truncated file", [&] {
            write_wav(wav_path);
            std::filesystem::resize_file(wav_path, 50);
            rejects([&] { shadow::inspect_wav(wav_path); }, "truncated PCM");
        });
        test("WAV rejects unsupported compression", [&] {
            write_wav(wav_path);
            { std::fstream file(wav_path, std::ios::in | std::ios::out | std::ios::binary);
              file.seekp(30); file.put('\3'); }  // PCM format starts at offset 30.
            rejects([&] { shadow::inspect_wav(wav_path); }, "float WAV");
        });
        test("WAV rejects missing file", [&] {
            rejects([&] { shadow::inspect_wav(temporary.path("missing.wav")); }, "missing WAV");
        });
#ifdef SHADOW_HAVE_ALSA
        if (const char* enabled = std::getenv("SHADOW_TEST_ALSA_NULL");
            enabled && std::string(enabled) == "1") {
            test("ALSA null API smoke (does not test speaker timing)", [&] {
                write_wav(wav_path, 1000);
                auto audio = shadow::make_wav_audio(wav_path, "null");
                audio->start(0);
                double previous = audio->position_s(0.01);
                require(previous >= 0 && previous <= 1, "valid sample position");
                audio->ended(0.01);
                near(audio->position_s(0.01), previous, "one service per same timestamp");
                audio->pause(0.02);
                const double paused = audio->position_s(1);
                near(audio->position_s(5), paused, "device pause holds position");
                audio->resume(5);
                previous = paused;
                bool finished = false;
                for (int tick = 1; tick <= 100; ++tick) {
                    const double now = 5.0 + tick * 0.02;
                    const double current = audio->position_s(now);
                    require(current >= previous && current <= 1.0, "device position monotonic");
                    previous = current;
                    if (audio->ended(now)) { finished = true; break; }
                }
                require(finished, "null stream reaches end");
                audio->stop(8);
                near(audio->position_s(8), 0, "device stop resets position");
                audio->start(8);
                require(!audio->ended(8), "device supports restart");
                audio->stop(9);
                rejects([&] { shadow::make_wav_audio(wav_path, "shadow_missing_audio_device"); },
                        "missing device must fail instead of silently using clock audio");
            });
        }
#endif
        std::cout << passed << " script/audio checks passed\n";
    } catch (...) {
        return 1;
    }
    return 0;
}
