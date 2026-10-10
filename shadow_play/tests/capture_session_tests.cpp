#include "shadow/capture_session.hpp"
#include <nlohmann/json.hpp>
#include <chrono>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <functional>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
using namespace shadow;
using Json = nlohmann::json;
void require(bool condition, const std::string& message) {
    if (!condition) throw std::runtime_error(message);
}
template <typename F> void rejects(F fn) {
    bool rejected = false;
    try { fn(); } catch (const std::exception&) { rejected = true; }
    require(rejected, "invalid operation was accepted");
}
Json config_json() {
    return {{"version", 1}, {"simulation_only", false},
        {"stage", {{"width_mm", 1000}, {"height_mm", 600}}}, {"reference_view", "rear"},
        {"axes", Json::array({
            {{"id", "neck_x"}, {"rod", "wusong_neck"}, {"unit", "demo"}, {"min", -1},
             {"max", 1}, {"initial", 0}, {"jog_step", 0.05}, {"max_step", 0.25}},
            {{"id", "tail_y"}, {"rod", "tiger_tail"}, {"unit", "demo"}, {"min", -1},
             {"max", 1}, {"initial", 0}, {"jog_step", 0.05}, {"max_step", 0.25}}})},
        {"slides", Json::array({{{"id", "slide"}, {"unit", "mm"}, {"value", 20}, {"state_kind", "commanded"}}})},
        {"points", Json::array({{{"id", "center"}, {"rod", "wusong_neck"},
                                {"axes", {{"neck_x", 0}, {"tail_y", 0}}}}})}};
}
CaptureConfig config() { return parse_capture_config(config_json().dump(), "test source.json"); }
Json controlled_config_json(bool mixed = false) {
    auto j = config_json();
    j["slides"] = Json::array({
        {{"id", "wusong_slide"}, {"unit", "demo"}, {"value", 0}, {"state_kind", "commanded"},
         {"controllable", true}, {"min", -1}, {"max", 1}, {"jog_step", 0.05}, {"max_step", 0.25}},
        {{"id", "tiger_slide"}, {"unit", "demo"}, {"value", 0}, {"state_kind", "commanded"},
         {"controllable", true}, {"min", -1}, {"max", 1}, {"jog_step", 0.05}, {"max_step", 0.25}}
    });
    if (mixed) j["slides"].push_back({{"id", "fixed_slide"}, {"unit", "mm"}, {"value", 20},
        {"state_kind", "fixed_assumption"}, {"assumption", "Manual entry; no position feedback was supplied"}});
    return j;
}
CaptureConfig controlled_config(bool mixed = false) { return parse_capture_config(controlled_config_json(mixed).dump()); }
struct Temp {
    std::filesystem::path path = std::filesystem::temp_directory_path() /
        ("shadow-capture-test-" + std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()));
    Temp() { std::filesystem::create_directories(path); }
    ~Temp() { std::error_code ignored; std::filesystem::remove_all(path, ignored); }
};
std::string read(const std::filesystem::path& path) {
    std::ifstream file(path, std::ios::binary); std::ostringstream out; out << file.rdbuf(); return out.str();
}
Json ack_json(const CaptureRequest& request, double neck = 0, double tail = 0) {
    return {{"version", 1}, {"type", "capture_ack"}, {"session_id", request.session_id},
        {"seq", request.seq}, {"accepted", true},
        {"adopted", Json::array({{{"axis_id", "neck_x"}, {"value", neck}, {"unit", "demo"}},
                                  {{"axis_id", "tail_y"}, {"value", tail}, {"unit", "demo"}}})},
        {"slides", Json::array({{{"id", "slide"}, {"unit", "mm"}, {"value", 21.5}, {"state_kind", "measured"}}})}};
}
Json controlled_ack(const CaptureRequest& request, double wusong, double tiger) {
    auto j = ack_json(request); j["version"] = 2;
    // Adapters may return a different order; state is normalized by ID.
    j["slides"] = Json::array({
        {{"id", "tiger_slide"}, {"unit", "demo"}, {"value", tiger}, {"state_kind", "measured"}},
        {{"id", "wusong_slide"}, {"unit", "demo"}, {"value", wusong}, {"state_kind", "commanded"}}
    });
    return j;
}
void test_config() {
    const auto c = config();
    require(c.reference_points_mm[2][0] == 1000 && c.reference_points_mm[2][1] == 600,
            "default stage corners are wrong");
    const std::vector<std::function<void(Json&)>> invalid{
        [](Json& j) { j["version"] = 2; }, [](Json& j) { j["version"] = 1.0; },
        [](Json& j) { j["stage"]["width_mm"] = 0; }, [](Json& j) { j["reference_view"] = "side"; },
        [](Json& j) { j["reference_points_mm"] = {{0, 0}, {1, 1}, {2, 2}, {3, 3}}; },
        [](Json& j) { j["axes"][1]["id"] = "neck_x"; },
        [](Json& j) { j["axes"][0]["rod"] = "unknown"; },
        [](Json& j) { j["axes"][0]["unit"] = ""; },
        [](Json& j) { j["axes"][0]["max_step"] = 0; },
        [](Json& j) { j["axes"][0]["jog_step"] = 0.5; },
        [](Json& j) { j["axes"][0]["initial"] = 2; },
        [](Json& j) { j["points"][0]["axes"].erase("tail_y"); },
        [](Json& j) { j["points"][0]["axes"]["ghost"] = 0; },
        [](Json& j) { j["slides"][0]["state_kind"] = "fixed_assumption"; },
        [](Json& j) { j["slides"].push_back(j["slides"][0]); },
        [](Json& j) { j["slides"] = Json::array(); },
        [](Json& j) { j["axes"] = Json::array(); },
        [](Json& j) { j["unrecognized"] = true; }
    };
    for (const auto& mutate : invalid) {
        auto j = config_json(); mutate(j); rejects([&] { parse_capture_config(j.dump()); });
    }
    auto bad = c; bad.axes[0].initial = std::numeric_limits<double>::quiet_NaN();
    rejects([&] { validate_capture_config(bad); });
    rejects([&] { parse_capture_config("{\"version\":1,\"version\":1}"); });
    rejects([&] { parse_capture_config("{broken}"); });
    auto no_plan = config_json(); no_plan.erase("points");
    auto front = config_json(); front["reference_view"] = "front";
    require(parse_capture_config(front.dump()).reference_view == "front", "front view rejected");
    require(parse_capture_config(no_plan.dump()).points.empty(), "omitted plan was not accepted");
    no_plan["points"] = Json::array();
    require(parse_capture_config(no_plan.dump()).points.empty(), "empty plan was not accepted");
}
void test_transition() {
    auto c = config(); const std::map<std::string, double> from{{"neck_x", 0}, {"tail_y", 0}};
    validate_capture_transition(c, from, {{"neck_x", 0.25}, {"tail_y", -0.25}});
    rejects([&] { validate_capture_transition(c, from, {{"neck_x", 0.251}, {"tail_y", 0}}); });
    rejects([&] { validate_capture_transition(c, from, {{"neck_x", 0}}); });
    rejects([&] { validate_capture_transition(c, from, {{"neck_x", 0}, {"tail_y", 2}}); });
    rejects([&] { validate_capture_transition(c, from,
        {{"neck_x", std::numeric_limits<double>::infinity()}, {"tail_y", 0}}); });
}
void test_ack() {
    const auto c = config(); CaptureRequest request; request.session_id = "s"; request.seq = 7;
    const auto good = ack_json(request, 0.7, -0.7);
    const auto state = parse_capture_ack(c, request, good.dump());
    require(state.axes[0].value == 0.7 && !state.feedback && state.confirmed,
            "adopted values or absent feedback were changed");
    auto null_feedback = good; null_feedback["feedback"] = nullptr;
    require(!parse_capture_ack(c, request, null_feedback.dump()).feedback, "null feedback was not preserved");
    auto feedback = good; feedback["feedback"] = Json::array({
        {{"axis_id", "neck_x"}, {"value", 0.68}, {"unit", "demo"}}});
    const auto measured = parse_capture_ack(c, request, feedback.dump());
    require(measured.feedback->at(0).value == 0.68 && measured.axes[0].value == 0.7,
            "feedback was conflated with adopted target");
    const std::vector<std::function<void(Json&)>> invalid{
        [](Json& j) { j["version"] = 0; }, [](Json& j) { j["type"] = "capture_target"; },
        [](Json& j) { j["session_id"] = "stale"; }, [](Json& j) { j["seq"] = 6; },
        [](Json& j) { j["seq"] = -1; }, [](Json& j) { j["accepted"] = false; },
        [](Json& j) { j["fault"] = "drive fault"; },
        [](Json& j) { j["adopted"].erase(1); },
        [](Json& j) { j["adopted"].push_back(j["adopted"][0]); },
        [](Json& j) { j["adopted"][0]["unit"] = "deg"; },
        [](Json& j) { j["adopted"][0]["value"] = 1.001; },
        [](Json& j) { j["feedback"] = Json::array(); },
        [](Json& j) { j["slides"] = Json::array(); },
        [](Json& j) { j["slides"][0]["unit"] = "demo"; },
        [](Json& j) { j["slides"][0].erase("state_kind"); },
        [](Json& j) { j["slides"][0]["state_kind"] = "fixed_assumption"; }
    };
    for (const auto& mutate : invalid) {
        auto j = good; mutate(j); rejects([&] { parse_capture_ack(c, request, j.dump()); });
    }
}
void test_external_sync_and_steps() {
    Temp temp; auto c = config(); c.simulation_only = true;
    rejects([&] { CaptureSession session(temp.path / "demo-external", c, "external"); });
    require(!std::filesystem::exists(temp.path / "demo-external"), "rejected session created files");
    c.simulation_only = false; CaptureSession session(temp.path / "external", c, "external");
    rejects([&] { session.make_request(session.adopted_axes()); });
    const auto sync = session.make_request(session.adopted_axes(), "capture_sync");
    require(Json::parse(sync.json)["type"] == "capture_sync", "sync request became movement");
    rejects([&] { session.make_request(session.adopted_axes(), "capture_sync"); });
    session.accept_ack(sync, ack_json(sync, 0.5).dump());
    require(session.synchronized() && session.adopted_axes().at("neck_x") == 0.5, "sync did not adopt current state");
    rejects([&] { session.make_request({{"neck_x", 0}, {"tail_y", 0}}); });
    auto target = session.make_request({{"neck_x", 0.75}, {"tail_y", 0}});
    session.accept_ack(target, ack_json(target, 0.7).dump());
    rejects([&] { session.make_request({{"neck_x", 0.44}, {"tail_y", 0}}); });
    target = session.make_request({{"neck_x", 0.5}, {"tail_y", 0}});
    auto wrong = ack_json(target); wrong["seq"] = sync.seq;
    rejects([&] { session.accept_ack(target, wrong.dump()); });
    require(!session.synchronized() && !session.state().accepted, "bad ACK did not lock external movement");
    rejects([&] { session.make_request(session.adopted_axes()); });
    const auto resync = session.make_request(session.adopted_axes(), "capture_sync");
    session.accept_ack(resync, ack_json(resync).dump());
    session.invalidate_external();
    rejects([&] { session.make_request(session.adopted_axes()); });
    require(read(temp.path / "external" / "requests.jsonl").find("capture_sync") != std::string::npos,
            "requests were not recorded");
}
void append32(std::vector<std::uint8_t>& bytes, std::uint32_t value) {
    for (int shift = 24; shift >= 0; shift -= 8) bytes.push_back(static_cast<std::uint8_t>(value >> shift));
}
void chunk(std::vector<std::uint8_t>& out, const std::string& type, const std::vector<std::uint8_t>& data) {
    append32(out, static_cast<std::uint32_t>(data.size()));
    const auto start = out.size(); out.insert(out.end(), type.begin(), type.end());
    out.insert(out.end(), data.begin(), data.end());
    std::uint32_t crc = 0xffffffffU;
    for (std::size_t i = start; i < out.size(); ++i) {
        crc ^= out[i]; for (int bit = 0; bit < 8; ++bit) crc = (crc >> 1) ^ ((crc & 1U) ? 0xedb88320U : 0U);
    }
    append32(out, crc ^ 0xffffffffU);
}
std::vector<std::uint8_t> png() {
    std::vector<std::uint8_t> bytes{137, 80, 78, 71, 13, 10, 26, 10};
    chunk(bytes, "IHDR", {0,0,0,2,0,0,0,2,8,0,0,0,0});
    // Valid zlib stream containing two unfiltered grayscale scanlines.
    chunk(bytes, "IDAT", {0x78,0x01,0x01,0x06,0x00,0xf9,0xff,0,0,0,0,0,0,0,6,0,1});
    chunk(bytes, "IEND", {}); return bytes;
}
std::vector<std::string> csv_columns(const std::string& row) {
    std::vector<std::string> result; std::string field; bool quoted = false;
    for (std::size_t i = 0; i < row.size(); ++i) {
        const char c = row[i];
        if (c == '"') {
            if (quoted && i + 1 < row.size() && row[i + 1] == '"') { field += '"'; ++i; }
            else quoted = !quoted;
        } else if (c == ',' && !quoted) { result.push_back(field); field.clear(); }
        else if (c != '\n' && c != '\r') field += c;
    }
    require(!quoted, "CSV quotes are unbalanced"); result.push_back(field); return result;
}
void test_sample_and_csv() {
    Temp temp; const auto c = config(); CaptureSession session(temp.path / "session", c, "simulation");
    rejects([&] { CaptureSession duplicate(temp.path / "session", c, "simulation"); });
    require(read(session.directory() / "config.snapshot.json") == c.source_json, "snapshot differs from source");
    const auto request = session.make_request({{"neck_x", 0.1}, {"tail_y", -0.1}});
    CaptureSample sample; sample.sample_id = "sample_001"; sample.rod = "tiger_tail"; sample.seq = request.seq;
    sample.pixel_x = 0.5; sample.pixel_y = 1; sample.image_width = sample.image_height = 2;
    sample.stage_x_mm = 500; sample.stage_y_mm = 300;
    sample.frame_path = "frames/sample_001.png"; sample.frozen_at = capture_utc_now();
    sample.frame_read_at = "2026-01-01T00:00:00Z";
    sample.calibration_id = "calibration,\"quoted\""; sample.state = session.state();
    const auto bytes = png();
    auto bad = sample; bad.pixel_x = 2;
    rejects([&] { session.record_sample(bad, bytes); });
    bad = sample; bad.stage_y_mm = std::numeric_limits<double>::quiet_NaN();
    rejects([&] { session.record_sample(bad, bytes); });
    bad = sample; bad.seq = request.seq + 1;
    rejects([&] { session.record_sample(bad, bytes); });
    bad = sample; bad.frame_path = "../escape.png";
    rejects([&] { session.record_sample(bad, bytes); });
    bad = sample; bad.state.axes[0].value = 0.11;
    rejects([&] { session.record_sample(bad, bytes); });
    bad = sample; bad.image_width = 3;
    rejects([&] { session.record_sample(bad, bytes); });
    auto corrupt = bytes; corrupt[45] ^= 1;
    rejects([&] { session.record_sample(sample, corrupt); });
    rejects([&] { session.record_sample(sample, {}); });
    require(read(session.directory() / "samples.jsonl").empty(), "bad samples reached database");
    session.record_sample(sample, bytes);
    const auto before = read(session.directory() / "samples.jsonl");
    const auto saved = Json::parse(before);
    require(saved["state"]["feedback"].is_null() && saved["state"]["axes"].size() == 2 &&
            saved["state"]["slides"].size() == 1 && saved["pixel"]["width"] == 2 &&
            saved["frame_read_at"] == *sample.frame_read_at && saved["frozen_at"] == sample.frozen_at,
            "authoritative record omitted state or image metadata");
    rejects([&] { session.record_sample(sample, bytes); });
    bad = sample; bad.sample_id = "second";
    rejects([&] { session.record_sample(bad, bytes); });
    require(read(session.directory() / "samples.jsonl") == before, "duplicate changed database");
    const auto csv = read(session.directory() / "samples.csv");
    const auto fields = csv_columns(csv.substr(csv.find('\n') + 1));
    require(fields.size() == 20 && fields[13] == sample.calibration_id && fields[19] == *sample.frame_read_at,
            "CSV did not retain quoted calibration id");
    require(Json::parse(fields[9]).size() == 2 && Json::parse(fields[10]).size() == 1 && fields[11] == "null",
            "CSV axis/slide/feedback state cannot be parsed");
    require(capture_csv_escape("a,b\"c\nd") == "\"a,b\"\"c\nd\"", "CSV escaping failed");
    require(capture_csv_escape("plain") == "plain", "plain CSV field changed");
}
void test_manual_slides() {
    Temp temp; CaptureSession session(temp.path / "manual", config(), "manual_unconfirmed");
    auto slides = session.state().slides;
    rejects([&] { session.update_manual_slides(slides); });
    slides[0].state_kind = "fixed_assumption";
    slides[0].assumption = "Manual entry; no position feedback was supplied";
    slides[0].value = 35.5; session.update_manual_slides(slides);
    session.make_request({{"neck_x", 0}, {"tail_y", 0}});
    require(session.state().slides[0].value == 35.5 && !session.state().confirmed &&
            !session.state().feedback && session.state().backend == "manual_unconfirmed",
            "manual state falsely claimed confirmation or feedback");
    session.make_request({{"neck_x", 0.8}, {"tail_y", -0.8}});
    require(session.adopted_axes().at("neck_x") == 0.8 && !session.state().confirmed,
            "manual retrospective entry was blocked by a motion step limit");
    slides[0].unit = "deg"; rejects([&] { session.update_manual_slides(slides); });
    CaptureSession simulation(temp.path / "sim", config(), "simulation");
    rejects([&] { simulation.update_manual_slides(simulation.state().slides); });
}
void test_slide_config_and_requests() {
    const std::vector<std::function<void(Json&)>> invalid{
        [](Json& j) { j["slides"][0].erase("min"); },
        [](Json& j) { j["slides"][0]["controllable"] = "true"; },
        [](Json& j) { j["slides"][0]["max"] = -1; },
        [](Json& j) { j["slides"][0]["value"] = 1.01; },
        [](Json& j) { j["slides"][0]["jog_step"] = 0; },
        [](Json& j) { j["slides"][0]["jog_step"] = 0.3; },
        [](Json& j) { j["slides"][0]["max_step"] = 0; },
        [](Json& j) { j["slides"][0]["controllable"] = false; },
        [](Json& j) { j["slides"][0]["state_kind"] = "fixed_assumption";
                      j["slides"][0]["assumption"] = "This is only an assumption"; }
    };
    for (const auto& mutate : invalid) {
        auto j = controlled_config_json(); mutate(j); rejects([&] { parse_capture_config(j.dump()); });
    }
    auto nonfinite = controlled_config(); nonfinite.slides[0].max_step = std::numeric_limits<double>::infinity();
    rejects([&] { validate_capture_config(nonfinite); });
    Temp temp; CaptureSession legacy(temp.path / "legacy", config(), "simulation");
    rejects([&] { legacy.make_request(legacy.adopted_axes(), "capture_target", {{"slide", 20.1}}); });
    const auto old = legacy.make_request(legacy.adopted_axes());
    require(old.version == 1 && !Json::parse(old.json).contains("slides"), "legacy request changed protocol");
    auto snapshot_config = controlled_config(true); snapshot_config.source_json.clear();
    CaptureSession session(temp.path / "simulation", snapshot_config, "simulation");
    const auto snapshot = load_capture_config(session.directory() / "config.snapshot.json");
    require(snapshot.slides[0].controllable && snapshot.slides[0].max_step == 0.25,
            "generated config snapshot lost control limits");
    const auto baseline = session.adopted_slides();
    rejects([&] { session.make_request(session.adopted_axes(), "capture_target", {{"ghost", 0.1}}); });
    rejects([&] { session.make_request(session.adopted_axes(), "capture_target", {{"fixed_slide", 20.1}}); });
    rejects([&] { session.make_request(session.adopted_axes(), "capture_target", {{"wusong_slide", 1.1}}); });
    rejects([&] { session.make_request(session.adopted_axes(), "capture_target", {{"wusong_slide", 0.251}}); });
    rejects([&] { session.make_request(session.adopted_axes(), "capture_target",
        {{"wusong_slide", std::numeric_limits<double>::quiet_NaN()}}); });
    require(session.adopted_slides() == baseline, "rejected slide request changed state");
    const auto request = session.make_request(session.adopted_axes(), "capture_target", {{"wusong_slide", 0.25}});
    const auto encoded = Json::parse(request.json);
    require(request.version == 2 && encoded["version"] == 2 && encoded["slides"].size() == 3 &&
            encoded["slides"][0]["value"] == 0.25 && encoded["slides"][0]["controllable"] == true &&
            encoded["slides"][2]["controllable"] == false, "group request omitted control or retained slide state");
    session.make_request(session.adopted_axes(), "capture_target", {{"tiger_slide", -0.25}});
    require(session.adopted_slides().at("wusong_slide") == 0.25 && session.adopted_slides().at("tiger_slide") == -0.25,
            "partial slide request changed an unspecified adopted slide");
    session.make_request(session.adopted_axes());
    require(session.adopted_slides().at("wusong_slide") == 0.25, "axis-only request reset adopted slides");
}
void test_slide_external_ack_and_steps() {
    Temp temp; const auto c = controlled_config(); CaptureSession session(temp.path / "external", c, "external");
    rejects([&] { session.make_request(session.adopted_axes(), "capture_target", {{"wusong_slide", 0.1}}); });
    rejects([&] { session.make_request(session.adopted_axes(), "capture_sync", {{"wusong_slide", 0.1}}); });
    auto sync = session.make_request(session.adopted_axes(), "capture_sync");
    require(sync.version == 2 && Json::parse(sync.json)["type"] == "capture_sync" &&
            Json::parse(sync.json)["slides"][0]["value"] == 0, "sync transmitted a slide movement");
    const auto good = controlled_ack(sync, 0.7, -0.4);
    const std::vector<std::function<void(Json&)>> invalid{
        [](Json& j) { j["version"] = 1; },
        [](Json& j) { j["slides"].erase(1); },
        [](Json& j) { j["slides"].push_back(j["slides"][0]); },
        [](Json& j) { j["slides"][0]["id"] = "unknown"; },
        [](Json& j) { j["slides"][0]["unit"] = "mm"; },
        [](Json& j) { j["slides"][0]["value"] = -1.01; },
        [](Json& j) { j["slides"][0]["controllable"] = false; },
        [](Json& j) { j["slides"][0]["state_kind"] = "fixed_assumption";
                      j["slides"][0]["assumption"] = "Unconfirmed"; }
    };
    for (const auto& mutate : invalid) {
        auto j = good; mutate(j); rejects([&] { parse_capture_ack(c, sync, j.dump()); });
    }
    session.accept_ack(sync, good.dump());
    require(session.state().slides[0].id == "wusong_slide" && session.state().slides[0].controllable &&
            session.adopted_slides().at("wusong_slide") == 0.7 && !session.state().feedback,
            "ACK slide identity, adopted values, or missing feedback were changed");
    rejects([&] { session.make_request(session.adopted_axes(), "capture_target", {{"wusong_slide", 0.44}}); });
    auto request = session.make_request(session.adopted_axes(), "capture_target", {{"wusong_slide", 0.9}});
    session.accept_ack(request, controlled_ack(request, 0.8, -0.4).dump());
    // The next step must use 0.8 adopted by the adapter, rather than 0.9 requested.
    request = session.make_request(session.adopted_axes(), "capture_target", {{"wusong_slide", 0.56}});
    auto bad_ack = controlled_ack(request, 0.56, -0.4); bad_ack["slides"][0]["value"] = -2;
    rejects([&] { session.accept_ack(request, bad_ack.dump()); });
    require(!session.synchronized(), "bad slide ACK did not lock movement");
    rejects([&] { session.make_request(session.adopted_axes(), "capture_target", {{"wusong_slide", 0.8}}); });
    sync = session.make_request(session.adopted_axes(), "capture_sync");
    session.accept_ack(sync, controlled_ack(sync, 0.8, -0.4).dump());
}
void test_controlled_manual_and_record() {
    Temp temp; CaptureSession session(temp.path / "manual", controlled_config(true), "manual_unconfirmed");
    auto slides = session.state().slides; slides[2].value = 35.5;
    session.update_manual_slides(slides);
    slides[0].value = 0.05; rejects([&] { session.update_manual_slides(slides); });
    const auto request = session.make_request(session.adopted_axes(), "capture_target", {{"wusong_slide", 0.8}});
    require(session.state().slides[0].value == 0.8 && session.state().slides[0].state_kind == "commanded" &&
            session.state().slides[2].value == 35.5 && !session.state().confirmed && !session.state().feedback,
            "manual commands lost fixed slide state or acquired false confirmation");
    rejects([&] { session.make_request(session.adopted_axes(), "capture_target", {{"wusong_slide", 2}}); });
    CaptureSample sample; sample.sample_id = "sample_controlled"; sample.rod = "wusong_neck"; sample.seq = request.seq;
    sample.image_width = sample.image_height = 2; sample.pixel_x = sample.pixel_y = 0.5;
    sample.stage_x_mm = 10; sample.stage_y_mm = 20; sample.frozen_at = capture_utc_now();
    sample.calibration_id = "calibration_controlled"; sample.frame_path = "frames/sample_controlled.png";
    sample.state = session.state();
    auto altered = sample; altered.state.slides[0].value = 0.7;
    rejects([&] { session.record_sample(altered, png()); });
    altered = sample; altered.state.slides[0].controllable = false;
    rejects([&] { session.record_sample(altered, png()); });
    session.record_sample(sample, png());
    const auto record = Json::parse(read(session.directory() / "samples.jsonl"));
    require(record["state"]["slides"][0]["value"] == 0.8 && record["state"]["slides"][0]["controllable"] == true &&
            record["state"]["slides"][2]["state_kind"] == "fixed_assumption" && record["state"]["confirmed"] == false,
            "saved sample omitted controlled/fixed slide states or confirmation flags");
    const auto csv = read(session.directory() / "samples.csv");
    const auto fields = csv_columns(csv.substr(csv.find('\n') + 1));
    require(Json::parse(fields[10])[0]["value"] == 0.8, "CSV lost adopted sliding state");
}
} // namespace
int main(int argc, char** argv) {
    try {
        test_config(); test_transition(); test_ack(); test_external_sync_and_steps();
        test_sample_and_csv(); test_manual_slides();
        test_slide_config_and_requests(); test_slide_external_ack_and_steps(); test_controlled_manual_and_record();
        if (argc > 1) {
            const auto demo = load_capture_config(argv[1]);
            require(demo.axes.size() == 10 && demo.slides.size() == 2 && demo.simulation_only,
                    "demo must have ten axes, two slides, and simulation_only");
            require(demo.slides[0].controllable && demo.slides[1].controllable &&
                    demo.slides[0].unit == "demo" && demo.slides[1].unit == "demo",
                    "demo must enable both normalized sliding controls");
            std::map<std::string, double> previous;
            for (const auto& axis : demo.axes) previous[axis.id] = axis.initial;
            for (const auto& point : demo.points) {
                validate_capture_transition(demo, previous, point.axes); previous = point.axes;
            }
        }
        std::cout << "capture session tests passed\n"; return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n'; return 1;
    }
}
