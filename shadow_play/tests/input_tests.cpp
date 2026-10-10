#include "shadow/input.hpp"

#include <nlohmann/json.hpp>

#include <chrono>
#include <cmath>
#include <cstdio>
#include <fstream>
#include <functional>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace {
using namespace shadow;

void require(bool value, const std::string& message) {
    if (!value) throw std::runtime_error(message);
}
void near(double actual, double expected) {
    require(std::isfinite(actual) && std::abs(actual - expected) < 1e-9,
            "numeric mismatch: " + std::to_string(actual) + " vs " + std::to_string(expected));
}
template<class Function> void rejects(Function function) {
    bool rejected = false;
    try { function(); } catch (const std::exception&) { rejected = true; }
    require(rejected, "malformed data was accepted");
}

std::string frame_text(const std::string& points = "{}", const std::string& seq = "1") {
    return "{\"version\":1,\"source\":\"camera\",\"seq\":" + seq + ",\"points\":" + points + "}";
}

InputFrame skeleton() {
    InputFrame frame;
    frame.source = InputSource::Camera;
    frame.seq = 42;
    frame.points = {
        {"pelvis", {0.6, 0.7, 1.0, true}},
        {"left_shoulder", {0.6, 0.4, 1.0, true}},
        {"right_shoulder", {0.4, 0.4, 1.0, true}},
        {"left_wrist", {0.8, 0.2, 1.0, true}},
        {"right_wrist", {0.2, 0.6, 1.0, true}}
    };
    return frame;
}

InputFrame camera_v2() {
    auto frame = skeleton();
    frame.version = 2;
    frame.session_id = "follow_20260923-A";
    frame.track_id = 7;
    frame.captured_s = 123.25;
    frame.detected = true;
    return frame;
}

struct ReplayFile {
    std::string path;
    explicit ReplayFile(const std::string& data) {
        const auto stamp = std::chrono::steady_clock::now().time_since_epoch().count();
        path = "shadow_input_test_" + std::to_string(stamp) + ".jsonl";
        std::ofstream stream(path);
        stream << data;
        if (!stream) throw std::runtime_error("cannot create replay test file");
    }
    ~ReplayFile() {
        std::remove(path.c_str());
    }
};

void test_parse_and_roundtrip() {
    auto input = skeleton();
    input.seq = std::numeric_limits<std::uint64_t>::max();
    input.points.at("right_wrist").valid = false;
    const auto output = parse_input_frame(serialize_input_frame(input));
    require(output.seq == input.seq, "uint64 sequence did not roundtrip");
    require(output.source == InputSource::Camera, "source changed");
    require(output.points.size() == 5, "landmarks changed");
    require(!output.points.at("right_wrist").valid, "valid flag changed");
    near(output.points.at("pelvis").x, 0.6);
    const auto omitted = parse_input_frame(frame_text());
    require(omitted.points.empty(), "missing points became fabricated landmarks");
    const auto default_valid = parse_input_frame(frame_text("{\"pelvis\":{\"x\":0,\"y\":1,\"confidence\":0.8}}"));
    require(default_valid.points.at("pelvis").valid, "valid default should be true");
}

void test_json_errors_and_duplicates() {
    for (const std::string& text : std::vector<std::string>{"", "null", "[]", "{", "{}", frame_text() + "garbage",
             "{\"version\":1,\"version\":1,\"source\":\"camera\",\"seq\":1,\"points\":{}}",
             frame_text("{\"pelvis\":{\"x\":0,\"x\":1,\"y\":0,\"confidence\":1}}"),
             frame_text("{\"pelvis\":{\"x\":0,\"y\":0,\"confidence\":1},\"pelvis\":{\"x\":1,\"y\":1,\"confidence\":1}}")}) {
        rejects([&] { parse_input_frame(text); });
    }
    rejects([] { parse_input_frame(std::string(65537, ' ')); });
}

void test_frame_field_validation() {
    for (const auto& seq : {"-1", "1.0", "1e0", "true", "null", "\"1\"", "18446744073709551616"}) {
        rejects([&] { parse_input_frame(frame_text("{}", seq)); });
    }
    for (const auto& text : {
             "{\"version\":1.0,\"source\":\"camera\",\"seq\":1,\"points\":{}}",
             "{\"version\":2,\"source\":\"camera\",\"seq\":1,\"points\":{}}",
             "{\"version\":1,\"source\":\"unknown\",\"seq\":1,\"points\":{}}",
             "{\"version\":1,\"source\":1,\"seq\":1,\"points\":{}}",
             "{\"version\":1,\"source\":\"camera\",\"seq\":1,\"points\":{},\"typo\":0}"}) {
        rejects([&] { parse_input_frame(text); });
    }
}

void test_camera_v2_roundtrip_and_replay() {
    auto input = camera_v2();
    input.seq = std::numeric_limits<std::uint64_t>::max();
    input.track_id = std::numeric_limits<std::uint64_t>::max();
    const auto wire = serialize_input_frame(input);
    const auto output = parse_input_frame(wire);
    require(output.version == 2 && output.source == InputSource::Camera, "v2 version/source changed");
    require(output.seq == input.seq && output.track_id == input.track_id, "v2 uint64 metadata changed");
    require(output.session_id == input.session_id && output.detected, "v2 session/detected changed");
    near(output.captured_s, input.captured_s);
    require(output.points.size() == input.points.size(), "v2 landmarks changed");
    ReplayFile replay("{\"arrival_ms\":20,\"frame\":" + wire + "}\n");
    const auto records = load_input_replay(replay.path);
    require(records[0].frame.version == 2 && records[0].frame.track_id == input.track_id &&
            records[0].frame.session_id == input.session_id && records[0].frame.detected,
            "recording lost v2 metadata");
    near(records[0].frame.captured_s, input.captured_s);
    input.detected = false;
    input.points.clear();
    input.track_id = 0;
    input.captured_s = 0;
    auto absent = parse_input_frame(serialize_input_frame(input));
    require(!absent.detected && absent.points.empty() && absent.track_id == 0,
            "absent-person heartbeat changed");
    input.track_id = 7;  // FOLLOW may retain its last track id during a short loss.
    require(parse_input_frame(serialize_input_frame(input)).track_id == 7, "loss must permit retained track id");
    input.detected = true;  // A detected person can have no usable landmarks.
    require(parse_input_frame(serialize_input_frame(input)).points.empty(), "empty detected pose rejected");
}

void test_camera_v2_schema_validation() {
    using Json = nlohmann::json;
    const auto good = Json::parse(serialize_input_frame(camera_v2()));
    for (const auto* field : {"version", "source", "seq", "points", "session_id", "track_id", "captured_s", "detected"}) {
        auto invalid = good;
        invalid.erase(field);
        rejects([&] { parse_input_frame(invalid.dump()); });
    }
    const std::vector<std::pair<std::string, Json>> invalid_fields = {
        {"version", 3}, {"source", "touch"}, {"session_id", ""},
        {"session_id", std::string(65, 'a')}, {"session_id", "a.b"},
        {"session_id", "a b"}, {"session_id", "a/b"}, {"session_id", "\u4eba"},
        {"session_id", 1}, {"track_id", -1}, {"track_id", 1.0}, {"track_id", 0},
        {"track_id", "1"}, {"track_id", true}, {"captured_s", -0.1},
        {"captured_s", "1"}, {"captured_s", true}, {"captured_s", nullptr},
        {"detected", 1}, {"detected", "true"}, {"detected", false}, {"unknown", 0}
    };
    for (const auto& entry : invalid_fields) {
        auto invalid = good;
        invalid[entry.first] = entry.second;
        rejects([&] { parse_input_frame(invalid.dump()); });
    }
    auto longest = camera_v2();
    longest.session_id = std::string(64, 'a');
    require(parse_input_frame(serialize_input_frame(longest)).session_id.size() == 64,
            "64-character session id rejected");
    auto legacy = Json::parse(frame_text());
    for (const auto* field : {"session_id", "track_id", "captured_s", "detected"}) {
        auto invalid = legacy;
        invalid[field] = good.at(field);
        rejects([&] { parse_input_frame(invalid.dump()); });
    }
    for (int metadata = 0; metadata < 4; ++metadata) {
        auto invalid = skeleton();
        if (metadata == 0) invalid.session_id = "unexpected";
        if (metadata == 1) invalid.track_id = 1;
        if (metadata == 2) invalid.captured_s = 0.1;
        if (metadata == 3) invalid.detected = true;
        rejects([&] { serialize_input_frame(invalid); });
    }
    for (double bad : {-1.0, std::numeric_limits<double>::quiet_NaN(),
                       std::numeric_limits<double>::infinity()}) {
        auto invalid = camera_v2();
        invalid.captured_s = bad;
        rejects([&] { serialize_input_frame(invalid); });
    }
    auto invalid = camera_v2();
    invalid.detected = false;
    rejects([&] { serialize_input_frame(invalid); });
    invalid = camera_v2();
    invalid.track_id = 0;
    rejects([&] { serialize_input_frame(invalid); });
    invalid = camera_v2();
    invalid.source = InputSource::Touch;
    rejects([&] { serialize_input_frame(invalid); });
    invalid = camera_v2();
    invalid.session_id = "bad session";
    rejects([&] { serialize_input_frame(invalid); });
}

void test_landmark_validation() {
    for (const auto& point : {
             "null", "[]", "{}", "{\"x\":0,\"y\":0}",
             "{\"x\":-0.1,\"y\":0,\"confidence\":1}",
             "{\"x\":0,\"y\":1.1,\"confidence\":1}",
             "{\"x\":0,\"y\":0,\"confidence\":-0.1}",
             "{\"x\":0,\"y\":0,\"confidence\":1.1}",
             "{\"x\":1e999,\"y\":0,\"confidence\":1}",
             "{\"x\":\"0\",\"y\":0,\"confidence\":1}",
             "{\"x\":true,\"y\":0,\"confidence\":1}",
             "{\"x\":0,\"y\":0,\"confidence\":1,\"valid\":0}",
             "{\"x\":0,\"y\":0,\"confidence\":1,\"unused\":3}"}) {
        rejects([&] { parse_input_frame(frame_text("{\"pelvis\":" + std::string(point) + "}")); });
    }
    rejects([] { parse_input_frame(frame_text("[]")); });
    rejects([] { parse_input_frame(frame_text("{\"\":{\"x\":0,\"y\":0,\"confidence\":1}}")); });
    auto invalid = skeleton();
    invalid.points.at("pelvis").x = std::numeric_limits<double>::quiet_NaN();
    rejects([&] { serialize_input_frame(invalid); });
}

void test_replay_validation() {
    const auto a = "{\"arrival_ms\":0,\"frame\":" + frame_text("{}", "12") + "}\n";
    const auto b = "{\"arrival_ms\":20.5,\"frame\":" + frame_text("{}", "11") + "}\n";
    ReplayFile good("\n" + a + b + b);
    const auto records = load_input_replay(good.path);
    require(records.size() == 3, "replay frame count wrong");
    near(records[1].arrival_s, 0.0205);
    require(records[1].frame.seq == 11, "loader must preserve stale sequence for controller");
    for (const auto& text : {
             std::string("\n"), b + a,
             "{\"arrival_ms\":-1,\"frame\":" + frame_text() + "}\n",
             "{\"arrival_ms\":0,\"arrival_ms\":1,\"frame\":" + frame_text() + "}\n",
             "{\"arrival_ms\":\"0\",\"frame\":" + frame_text() + "}\n",
             "{\"arrival_ms\":0,\"frame\":" + frame_text() + ",\"extra\":0}\n"}) {
        ReplayFile invalid(text);
        rejects([&] { load_input_replay(invalid.path); });
    }
}

void test_retarget_sign_scale_and_tiger() {
    const auto result = Retargeter{}.map(skeleton());
    near(result.at(RodId::WusongNeck).x, 0.0);
    near(result.at(RodId::WusongNeck).y, 0.2);
    near(result.at(RodId::WusongLeft).x, 0.5);
    near(result.at(RodId::WusongLeft).y, 0.5);
    near(result.at(RodId::WusongRight).x, -0.5);
    near(result.at(RodId::WusongRight).y, -0.5);
    require(result.at(RodId::TigerHead).valid && result.at(RodId::TigerTail).valid, "tiger must be explicitly neutral");
    near(result.at(RodId::TigerHead).x, 0.0);
    auto touch = skeleton();
    touch.source = InputSource::Touch;
    near(Retargeter{}.map(touch).at(RodId::WusongLeft).x, result.at(RodId::WusongLeft).x);
}

void test_mirror_keeps_anatomical_labels() {
    RetargetConfig config;
    config.mirror_x = true;
    auto frame = skeleton();
    frame.points["neck"] = {0.6, 0.4, 1.0, true};
    const auto result = Retargeter{config}.map(frame);
    near(result.at(RodId::WusongLeft).x, -0.5);
    near(result.at(RodId::WusongLeft).y, 0.5);
    near(result.at(RodId::WusongRight).x, 0.5);
    near(result.at(RodId::WusongNeck).x, -0.2);
}

void test_missing_and_low_confidence_are_local() {
    auto frame = skeleton();
    frame.points.erase("left_wrist");
    auto result = Retargeter{}.map(frame);
    require(!result.at(RodId::WusongLeft).valid, "missing wrist should invalidate its rod");
    require(result.at(RodId::WusongRight).valid && result.at(RodId::WusongNeck).valid,
            "missing wrist invalidated unrelated rods");
    frame.points.at("right_wrist").confidence = 0.49;
    result = Retargeter{}.map(frame);
    require(!result.at(RodId::WusongRight).valid, "low-confidence wrist accepted");
    frame.points.at("right_wrist").confidence = 0.5;
    require(Retargeter{}.map(frame).at(RodId::WusongRight).valid, "threshold equality should be accepted");
    frame.points.at("left_shoulder").valid = false;
    require(!Retargeter{}.map(frame).at(RodId::WusongNeck).valid, "invalid shoulder midpoint accepted");
}

void test_shoulder_loss_and_scale_protection() {
    auto frame = skeleton();
    frame.points.at("left_shoulder").x = frame.points.at("right_shoulder").x;
    auto result = Retargeter{}.map(frame);
    require(!result.at(RodId::WusongLeft).valid && !result.at(RodId::WusongRight).valid,
            "zero shoulder width yielded valid hands");
    require(result.at(RodId::WusongNeck).valid, "zero shoulder width should still allow neck position");
    frame = skeleton();
    frame.points.at("right_shoulder").confidence = 0.0;
    result = Retargeter{}.map(frame);
    require(!result.at(RodId::WusongLeft).valid && !result.at(RodId::WusongRight).valid,
            "unavailable width should invalidate both hands");
    require(!result.at(RodId::WusongNeck).valid, "one low-confidence shoulder yielded valid neck");
    frame = skeleton();
    frame.points.at("left_wrist").x = std::numeric_limits<double>::infinity();
    require(!Retargeter{}.map(frame).at(RodId::WusongLeft).valid, "non-finite programmatic input accepted");
}

void test_retarget_bounds_and_config() {
    RetargetConfig config;
    config.hand_span_shoulders = 0.1;
    const auto result = Retargeter{config}.map(skeleton());
    near(result.at(RodId::WusongLeft).x, 1.0);
    near(result.at(RodId::WusongRight).y, -1.0);
    for (const double bad : {0.0, -1.0, std::numeric_limits<double>::infinity(),
                             std::numeric_limits<double>::quiet_NaN()}) {
        config.hand_span_shoulders = bad;
        rejects([&] { Retargeter unused{config}; });
    }
    config = {};
    config.min_shoulder_width = 0.0;
    rejects([&] { Retargeter unused{config}; });
    config = {};
    config.confidence_threshold = 1.1;
    rejects([&] { Retargeter unused{config}; });
}

void test_neck_rest_origin_calibration() {
    RetargetConfig config;
    config.neck_origin_x = 0.6;
    config.neck_origin_y = 0.7;
    auto frame = skeleton();
    frame.points["neck"] = {0.6, 0.7, 1.0, true};
    const auto rest = Retargeter{config}.map(frame);
    near(rest.at(RodId::WusongNeck).x, 0.0);
    near(rest.at(RodId::WusongNeck).y, 0.0);
    frame.points.at("neck").x = 0.7;
    frame.points.at("neck").y = 0.6;
    const auto moved = Retargeter{config}.map(frame);
    near(moved.at(RodId::WusongNeck).x, 0.2);
    near(moved.at(RodId::WusongNeck).y, 0.2);
    near(moved.at(RodId::WusongLeft).x, rest.at(RodId::WusongLeft).x);
    for (const double bad : {-0.1, 1.1, std::numeric_limits<double>::quiet_NaN(),
                             std::numeric_limits<double>::infinity()}) {
        config = {};
        config.neck_origin_x = bad;
        rejects([&] { Retargeter unused{config}; });
        config = {};
        config.neck_origin_y = bad;
        rejects([&] { Retargeter unused{config}; });
    }
}

void test_neck_selection_and_hip_independence() {
    auto frame = skeleton();
    frame.points["head"] = {0.9, 0.1, 1.0, true};
    frame.points["left_hip"] = {0.6, 0.8, 1.0, true};
    frame.points["right_hip"] = {0.4, 0.8, 1.0, true};
    const auto from_shoulders = Retargeter{}.map(frame).at(RodId::WusongNeck);
    near(from_shoulders.x, 0.0);
    near(from_shoulders.y, 0.2);
    frame.points.at("pelvis") = {0.0, 0.0, 1.0, true};
    frame.points.at("left_hip") = {1.0, 1.0, 1.0, true};
    frame.points.at("right_hip") = {1.0, 1.0, 1.0, true};
    near(Retargeter{}.map(frame).at(RodId::WusongNeck).y, from_shoulders.y);
    frame.points["neck"] = {0.65, 0.3, 0.5, true};
    const auto explicit_neck = Retargeter{}.map(frame).at(RodId::WusongNeck);
    near(explicit_neck.x, 0.3);
    near(explicit_neck.y, 0.4);
    frame.points.at("neck").confidence = 0.49;
    near(Retargeter{}.map(frame).at(RodId::WusongNeck).y, from_shoulders.y);
    frame.points.at("left_shoulder").confidence = 0.49;
    require(!Retargeter{}.map(frame).at(RodId::WusongNeck).valid,
            "midpoint confidence must depend on both shoulders");
    frame.points.at("left_shoulder").confidence = 0.5;
    require(Retargeter{}.map(frame).at(RodId::WusongNeck).valid,
            "midpoint threshold equality should be accepted");
    frame.points.erase("right_shoulder");
    require(!Retargeter{}.map(frame).at(RodId::WusongNeck).valid,
            "missing shoulder fell back to head or hips");
    frame.points.at("neck").confidence = 1.0;
    require(Retargeter{}.map(frame).at(RodId::WusongNeck).valid,
            "explicit usable neck incorrectly requires shoulders");
    frame.points.at("neck").valid = false;
    require(!Retargeter{}.map(frame).at(RodId::WusongNeck).valid, "invalid explicit neck accepted");
}

}  // namespace

int main() {
    const std::vector<std::pair<const char*, std::function<void()>>> tests = {
        {"parse and roundtrip", test_parse_and_roundtrip},
        {"JSON errors and duplicates", test_json_errors_and_duplicates},
        {"frame field validation", test_frame_field_validation},
        {"camera v2 roundtrip and replay", test_camera_v2_roundtrip_and_replay},
        {"camera v2 strict schema", test_camera_v2_schema_validation},
        {"landmark validation", test_landmark_validation},
        {"replay validation", test_replay_validation},
        {"retarget signs and scale", test_retarget_sign_scale_and_tiger},
        {"mirror and anatomical labels", test_mirror_keeps_anatomical_labels},
        {"local confidence and missing points", test_missing_and_low_confidence_are_local},
        {"shoulder scale protection", test_shoulder_loss_and_scale_protection},
        {"retarget bounds and config", test_retarget_bounds_and_config},
        {"neck resting origin calibration", test_neck_rest_origin_calibration},
        {"neck selection and hip independence", test_neck_selection_and_hip_independence}
    };
    int failed = 0;
    for (const auto& test : tests) {
        try { test.second(); std::cout << "PASS " << test.first << '\n'; }
        catch (const std::exception& error) {
            ++failed;
            std::cerr << "FAIL " << test.first << ": " << error.what() << '\n';
        }
    }
    std::cout << tests.size() - failed << '/' << tests.size() << " input test groups passed\n";
    return failed ? 1 : 0;
}
