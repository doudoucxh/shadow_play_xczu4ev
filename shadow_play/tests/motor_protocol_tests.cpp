#include "shadow/motor_backend.hpp"
#include <nlohmann/json.hpp>

#include <cmath>
#include <functional>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace {
using namespace shadow;
using Json = nlohmann::json;

void require(bool value, const std::string& why) {
    if (!value) throw std::runtime_error(why);
}
template<class Function> void rejects(Function function) {
    bool rejected = false;
    try { function(); } catch (const std::exception&) { rejected = true; }
    require(rejected, "invalid operation accepted");
}

ControlTick frame() {
    ControlTick tick;
    tick.time_s = 1.25;
    tick.mode = ShowMode::Camera;
    tick.playback_s = 0.0;
    tick.axes = {
        {"neck_pan", RodId::WusongNeck, 81.125, 145.0,
         InputState::TrackingOrHolding, true, false, true},
        {"left_pan", RodId::WusongLeft, 100.0, 100.0,
         InputState::TrackingOrHolding, false, false, false},
        {"right_pan", RodId::WusongRight, 95.0, 95.0,
         InputState::TrackingOrHolding, false, false, false},
        {"ear_pan", RodId::TigerHead, 90.0, 90.0,
         InputState::NoInput, false, false, false},
        {"tail_pan", RodId::TigerTail, 70.0, 70.0,
         InputState::ReturningToNeutral, false, true, false}
    };
    return tick;
}

void test_grouped_targets_preserve_final_angle_and_diagnostics() {
    const auto source = frame();
    const auto text = serialize_motor_frame(source, std::numeric_limits<std::uint64_t>::max());
    require(text.find('\n') == std::string::npos, "serializer must not append newline");
    const auto json = Json::parse(text);
    require(json.at("version") == 1 && json.at("type") == "motor_targets", "wrong contract");
    require(json.at("seq").get<std::uint64_t>() == std::numeric_limits<std::uint64_t>::max(),
            "sequence lost integer precision");
    require(json.at("time_s") == source.time_s && json.at("playback_s") == 0.0,
            "clock changed");
    require(json.at("mode") == "camera" && json.at("paused") == false, "mode changed");
    const auto& axes = json.at("axes");
    require(axes.size() == 5, "frame must preserve arbitrary configured axis count");
    const char* rods[] = {"wusong_neck", "wusong_left", "wusong_right", "tiger_head", "tiger_tail"};
    for (std::size_t i = 0; i < axes.size(); ++i) {
        require(axes[i].at("axis_id") == source.axes[i].axis_id, "axis order or ID changed");
        require(axes[i].at("rod") == rods[i], "attachment identity changed");
        require(axes[i].at("angle_deg") == source.axes[i].angle_deg, "final command changed");
        require(!axes[i].contains("limited_target_deg") && !axes[i].contains("pwm"),
                "diagnostic pre-filter target or invented PWM exported");
    }
    require(axes[0].at("angle_deg") != source.axes[0].limited_target_deg,
            "pre-filter target was used as motor command");
    require(axes[0].at("input_state") == "tracking_or_holding" &&
            axes[0].at("input_clamped") == true && axes[0].at("angle_limited") == false &&
            axes[0].at("speed_limited") == true, "diagnostics lost");
    auto paused = source;
    paused.mode = ShowMode::Script;
    paused.paused = true;
    paused.playback_s = 12.5;
    paused.axes[0].input_state = InputState::CommandHeld;
    const auto paused_json = Json::parse(serialize_motor_frame(paused, 1));
    require(paused_json.at("mode") == "script" && paused_json.at("paused") == true &&
            paused_json.at("playback_s") == 12.5 &&
            paused_json.at("axes")[0].at("input_state") == "command_held",
            "pause erased the actual mode or held-state diagnostic");
    for (const auto mode : {ShowMode::Stopped, ShowMode::Script, ShowMode::Touch, ShowMode::Camera}) {
        auto tick = source;
        tick.mode = mode;
        require(Json::parse(serialize_motor_frame(tick, 0)).at("mode") == show_mode_name(mode),
                "valid mode cannot be exported");
    }
}

class CountingBuffer : public std::stringbuf {
public:
    int flushes = 0;
    bool fail_flush = false;
    int sync() override {
        ++flushes;
        return fail_flush ? -1 : 0;
    }
};

void test_jsonl_boundaries_sequence_and_flush() {
    CountingBuffer buffer;
    std::ostream output(&buffer);
    JsonlMotorBackend backend(output);
    require(buffer.str().empty(), "JSONL output unexpectedly has CSV header");
    auto tick = frame();
    backend.send(tick);
    tick.axes.resize(1);
    tick.time_s += 0.02;
    backend.send(tick);
    require(buffer.flushes == 2, "each frame must be flushed");
    std::istringstream input(buffer.str());
    std::string first, second, extra;
    require(static_cast<bool>(std::getline(input, first)) &&
            static_cast<bool>(std::getline(input, second)) && !std::getline(input, extra),
            "not exactly one JSON line per tick");
    require(Json::parse(first).at("seq") == 1 && Json::parse(second).at("seq") == 2,
            "backend sequence does not start at 1 and increase");
    require(Json::parse(first).at("axes").size() == 5 &&
            Json::parse(second).at("axes").size() == 1, "serializer assumed ten axes");
    backend.shutdown();
    require(buffer.flushes == 3, "shutdown did not flush");
}

void test_bad_frame_emits_nothing_and_does_not_consume_sequence() {
    std::ostringstream output;
    JsonlMotorBackend backend(output);
    const auto valid = frame();
    const std::vector<std::function<void(ControlTick&)>> corruptions = {
        [](ControlTick& t) { t.time_s = std::numeric_limits<double>::infinity(); },
        [](ControlTick& t) { t.time_s = -0.1; },
        [](ControlTick& t) { t.playback_s = std::numeric_limits<double>::quiet_NaN(); },
        [](ControlTick& t) { t.playback_s = -0.1; },
        [](ControlTick& t) { t.mode = static_cast<ShowMode>(99); },
        [](ControlTick& t) { t.axes.clear(); },
        [](ControlTick& t) { t.axes.back().axis_id.clear(); },
        [](ControlTick& t) { t.axes.back().axis_id = "bad,id"; },
        [](ControlTick& t) { t.axes.back().axis_id = t.axes.front().axis_id; },
        [](ControlTick& t) { t.axes.back().rod = static_cast<RodId>(99); },
        [](ControlTick& t) { t.axes.back().angle_deg = std::numeric_limits<double>::infinity(); },
        [](ControlTick& t) { t.axes.back().input_state = static_cast<InputState>(99); }
    };
    for (const auto& corrupt : corruptions) {
        auto bad = valid;
        corrupt(bad);
        rejects([&] { backend.send(bad); });
        require(output.str().empty(), "invalid late axis emitted a partial frame");
    }
    backend.send(valid);
    require(Json::parse(output.str()).at("seq") == 1, "failed validation consumed sequence");
}

void test_stream_errors_propagate() {
    std::ostringstream broken;
    broken.setstate(std::ios::badbit);
    rejects([&] { JsonlMotorBackend backend(broken); });
    CountingBuffer buffer;
    std::ostream output(&buffer);
    JsonlMotorBackend backend(output);
    buffer.fail_flush = true;
    rejects([&] { backend.send(frame()); });
    rejects([&] { backend.shutdown(); });
}
} // namespace

int main() {
    const std::vector<std::pair<const char*, std::function<void()>>> tests = {
        {"grouped final-angle contract", test_grouped_targets_preserve_final_angle_and_diagnostics},
        {"JSONL sequence and flush", test_jsonl_boundaries_sequence_and_flush},
        {"invalid frame is rejected before output", test_bad_frame_emits_nothing_and_does_not_consume_sequence},
        {"stream failure propagation", test_stream_errors_propagate}
    };
    int failures = 0;
    for (const auto& test : tests) {
        try { test.second(); std::cout << "PASS " << test.first << '\n'; }
        catch (const std::exception& error) {
            ++failures;
            std::cerr << "FAIL " << test.first << ": " << error.what() << '\n';
        }
    }
    return failures ? 1 : 0;
}
