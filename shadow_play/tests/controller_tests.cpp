#include "shadow/controller.hpp"
#include "shadow/motor_backend.hpp"
#include "shadow/runtime_io.hpp"

#include <chrono>
#include <cmath>
#include <cstdio>
#include <fstream>
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

void require(bool value, const std::string& why) {
    if (!value) throw std::runtime_error(why);
}
void near(double actual, double expected, double tolerance = 1e-9) {
    require(std::isfinite(actual) && std::abs(actual - expected) <= tolerance,
            "expected " + std::to_string(expected) + ", got " + std::to_string(actual));
}
template<class Function> void rejects(Function function) {
    bool rejected = false;
    try { function(); } catch (const std::exception&) { rejected = true; }
    require(rejected, "invalid operation was accepted");
}

struct TempFile {
    std::string path;
    explicit TempFile(const std::string& text) {
        static unsigned serial = 0;
        const auto stamp = std::chrono::steady_clock::now().time_since_epoch().count();
        path = "shadow_controller_test_" + std::to_string(stamp) + "_" +
               std::to_string(serial++) + ".tmp";
        std::ofstream stream(path);
        stream << text;
        if (!stream) throw std::runtime_error("cannot create test file");
    }
    ~TempFile() { std::remove(path.c_str()); }
};

AxisCalibration body_axis(double speed = 10000.0) {
    return {"body_x", RodId::WusongNeck, 90.0, 30.0, 150.0, 30.0, 0.0, speed, 0.0};
}
Script simple_script() {
    Script script;
    script.duration_s = 2.0;
    ShadowPose pose;
    for (auto& rod : pose.rods) rod = {1.0, 0.0, true};
    script.frames = {{0.0, pose}, {2.0, pose}};
    return script;
}
ShowController controller(double speed = 10000.0) {
    return ShowController(simple_script(), {body_axis(speed)}, {90.0}, make_clock_audio(2.0));
}
InputFrame body_frame(InputSource source, std::uint64_t seq, double x = 1.0) {
    InputFrame frame;
    frame.source = source;
    frame.seq = seq;
    frame.points.emplace("neck", Landmark{x, 0.5, 1.0, true});
    return frame;
}

InputFrame camera_v2(std::uint64_t seq, std::uint64_t track = 1,
                     const std::string& session = "camera_A", double x = 1.0) {
    auto frame = body_frame(InputSource::Camera, seq, x);
    frame.version = 2;
    frame.session_id = session;
    frame.track_id = track;
    frame.captured_s = 100.0 + seq * 0.03;
    frame.detected = true;
    return frame;
}

void test_v2_restart_requires_explicit_reset() {
    auto show = controller();
    show.set_mode(ShowMode::Camera, 0.0);
    require(show.receive(camera_v2(100), 0.01) == ReceiveResult::Accepted, "initial session rejected");
    near(show.tick(0.02).axes[0].angle_deg, 120.0);
    require(show.receive(camera_v2(1, 1, "camera_B"), 0.03) == ReceiveResult::InputResetRequired,
            "new process reused previous session state");
    require(show.mode() == ShowMode::Stopped, "session change did not stop active camera");
    near(show.tick(0.04).axes[0].angle_deg, 90.0);
    show.set_mode(ShowMode::Camera, 0.05);
    require(show.receive(camera_v2(101), 0.055) == ReceiveResult::InputResetRequired,
            "delayed original session bypassed a required reset");
    require(show.receive(camera_v2(2, 1, "camera_B"), 0.06) == ReceiveResult::InputResetRequired,
            "rearm alone silently adopted a new session");
    show.reset_input_sequences(0.07);
    show.set_mode(ShowMode::Camera, 0.07);
    require(show.receive(camera_v2(1, 1, "camera_B", 0.0), 0.08) == ReceiveResult::Accepted,
            "explicit reset did not accept restarted seq");
    near(show.tick(0.09).axes[0].angle_deg, 60.0);
    require(show.receive(body_frame(InputSource::Camera, 999), 0.10) == ReceiveResult::InputResetRequired,
            "v1 bypassed the bound v2 session");
}

void test_v2_new_person_stops_until_rearmed() {
    auto show = controller();
    show.set_mode(ShowMode::Camera, 0.0);
    show.receive(camera_v2(1), 0.01);
    near(show.tick(0.02).axes[0].angle_deg, 120.0);
    require(show.receive(camera_v2(2, 2, "camera_A", 0.0), 0.03) == ReceiveResult::TrackingChanged,
            "new person was not detected");
    require(show.mode() == ShowMode::Stopped, "new person's motion was accepted without rearm");
    near(show.tick(0.04).axes[0].angle_deg, 90.0);
    require(show.receive(camera_v2(3, 2), 0.05) == ReceiveResult::InactiveSource,
            "person change automatically resumed motion");
    show.set_mode(ShowMode::Camera, 0.06);
    require(show.receive(camera_v2(4, 2, "camera_A", 0.0), 0.07) == ReceiveResult::Accepted,
            "explicit rearm failed");
    near(show.tick(0.08).axes[0].angle_deg, 60.0);
    require(show.receive(camera_v2(5, 1), 0.09) == ReceiveResult::DuplicateOrOld,
            "old track resumed after rearm");
    require(show.receive(camera_v2(5, 2), 0.10) == ReceiveResult::Accepted,
            "rejected old track consumed the sequence");
}

void test_v2_loss_frames_and_inactive_session_change() {
    auto show = controller();
    show.set_mode(ShowMode::Camera, 0.0);
    auto loss = camera_v2(1, 0);
    loss.detected = false;
    loss.points.clear();
    require(show.receive(loss, 0.01) == ReceiveResult::Accepted, "initial no-person frame rejected");
    require(show.receive(camera_v2(2), 0.02) == ReceiveResult::Accepted, "first person needs unnecessary rearm");
    near(show.tick(0.03).axes[0].angle_deg, 120.0);
    loss.seq = 3;
    loss.track_id = 1;
    show.receive(loss, 0.29);
    near(show.tick(0.35).axes[0].angle_deg, 90.0);
    require(show.receive(camera_v2(4, 2), 0.36) == ReceiveResult::TrackingChanged,
            "person reacquisition inherited previous control");
    show.restart(0.4);
    require(show.receive(camera_v2(1, 1, "another_process"), 0.41) == ReceiveResult::InputResetRequired,
            "inactive session mismatch undetected");
    require(show.mode() == ShowMode::Script, "inactive camera stopped the script");
}

void test_pause_holds_last_command_through_timeout() {
    auto show = controller(10.0);
    show.set_mode(ShowMode::Script, 0.0);
    const auto before = show.tick(0.1);
    near(before.axes[0].angle_deg, 90.5);
    show.pause(0.1);
    for (double time : {0.1, 0.4, 1.0, 100.0}) {
        const auto paused = show.tick(time);
        require(paused.paused && paused.mode == ShowMode::Script, "pause lost script state");
        near(paused.playback_s, 0.1);
        near(paused.axes[0].angle_deg, before.axes[0].angle_deg);
        require(paused.axes[0].input_state == InputState::CommandHeld, "pause must report held command");
    }
}

void test_resume_has_no_elapsed_pause_catchup() {
    auto show = controller(10.0);
    show.restart(0.0);
    const auto before = show.tick(0.1);
    show.pause(0.1);
    show.tick(100.0);
    show.resume(100.0);
    auto tick = show.tick(100.0);
    near(tick.axes[0].angle_deg, before.axes[0].angle_deg);
    near(tick.playback_s, 0.1);
    tick = show.tick(100.02);
    near(tick.playback_s, 0.12);
    near(tick.axes[0].angle_deg, before.axes[0].angle_deg + 0.2);
    require(!tick.paused && tick.mode == ShowMode::Script, "resume failed");
}

void test_script_completion_and_restart() {
    auto show = controller();
    show.restart(0.0);
    near(show.tick(0.1).axes[0].angle_deg, 120.0);
    const auto ended = show.tick(2.0);
    require(ended.mode == ShowMode::Stopped && !ended.paused, "completion did not stop");
    near(ended.playback_s, 2.0);
    near(ended.axes[0].angle_deg, 90.0);
    show.restart(4.0);
    const auto restarted = show.tick(4.02);
    require(restarted.mode == ShowMode::Script, "restart failed");
    near(restarted.playback_s, 0.02);
    near(restarted.axes[0].angle_deg, 120.0);
}

void test_switch_mode_discards_previous_targets() {
    auto show = controller();
    show.set_mode(ShowMode::Touch, 0.0);
    show.receive(body_frame(InputSource::Touch, 1), 0.01);
    near(show.tick(0.02).axes[0].angle_deg, 120.0);
    show.set_mode(ShowMode::Camera, 0.02);
    const auto fresh_mode = show.tick(0.04);
    near(fresh_mode.axes[0].angle_deg, 90.0);
    require(fresh_mode.axes[0].input_state == InputState::NoInput, "old input survived mode switch");
    show.receive(body_frame(InputSource::Camera, 1, 0.0), 0.05);
    near(show.tick(0.06).axes[0].angle_deg, 60.0);
    show.set_mode(ShowMode::Stopped, 0.06);
    near(show.tick(0.08).axes[0].angle_deg, 90.0);
}

void test_source_selection_and_independent_sequences() {
    auto show = controller();
    show.set_mode(ShowMode::Touch, 0.0);
    require(show.receive(body_frame(InputSource::Camera, 100), 0.01) == ReceiveResult::InactiveSource,
            "inactive source was accepted");
    near(show.tick(0.02).axes[0].angle_deg, 90.0);
    require(show.receive(body_frame(InputSource::Touch, 1), 0.03) == ReceiveResult::Accepted,
            "another source's high seq rejected touch");
    near(show.tick(0.04).axes[0].angle_deg, 120.0);
    show.set_mode(ShowMode::Camera, 0.04);
    require(show.receive(body_frame(InputSource::Camera, 100), 0.05) == ReceiveResult::DuplicateOrOld,
            "previously inactive frame could be replayed into new mode");
    near(show.tick(0.06).axes[0].angle_deg, 90.0);
    require(show.receive(body_frame(InputSource::Camera, 101, 0.0), 0.07) == ReceiveResult::Accepted,
            "fresh camera sequence rejected");
    near(show.tick(0.08).axes[0].angle_deg, 60.0);
}

void test_duplicate_frames_do_not_refresh_timeout() {
    auto show = controller();
    show.set_mode(ShowMode::Touch, 0.0);
    show.receive(body_frame(InputSource::Touch, 10), 0.01);
    near(show.tick(0.02).axes[0].angle_deg, 120.0);
    require(show.receive(body_frame(InputSource::Touch, 10), 0.29) == ReceiveResult::DuplicateOrOld,
            "duplicate accepted");
    require(show.receive(body_frame(InputSource::Touch, 9), 0.30) == ReceiveResult::DuplicateOrOld,
            "backward sequence accepted");
    const auto stale = show.tick(0.35);
    near(stale.axes[0].angle_deg, 90.0);
    require(stale.axes[0].input_state == InputState::ReturningToNeutral,
            "duplicate refreshed last-good timestamp");
    require(show.receive(body_frame(InputSource::Touch, 11), 0.36) == ReceiveResult::Accepted,
            "fresh sequence after timeout rejected");
    near(show.tick(0.38).axes[0].angle_deg, 120.0);
}

void test_sequence_reset_requires_stop() {
    auto show = controller();
    show.set_mode(ShowMode::Touch, 0.0);
    show.receive(body_frame(InputSource::Touch, 10), 0.01);
    rejects([&] { show.reset_input_sequences(0.02); });
    show.set_mode(ShowMode::Stopped, 0.02);
    require(show.receive(body_frame(InputSource::Touch, 0), 0.03) == ReceiveResult::DuplicateOrOld,
            "mode change implicitly reset sequence");
    show.reset_input_sequences(0.04);
    show.set_mode(ShowMode::Touch, 0.04);
    require(show.receive(body_frame(InputSource::Touch, 0), 0.05) == ReceiveResult::Accepted,
            "explicit producer reset did not accept sequence zero");
}

void test_malformed_cpp_frame_does_not_poison_sequence() {
    auto show = controller();
    show.set_mode(ShowMode::Touch, 0.0);
    auto frame = body_frame(InputSource::Touch, 5);
    frame.points.at("neck").x = std::numeric_limits<double>::quiet_NaN();
    rejects([&] { show.receive(frame, 0.01); });
    frame.points.at("neck").x = 2.0;
    rejects([&] { show.receive(frame, 0.01); });
    frame.points.at("neck").x = 1.0;
    require(show.receive(frame, 0.01) == ReceiveResult::Accepted,
            "invalid frame consumed sequence number");
    frame.source = static_cast<InputSource>(99);
    rejects([&] { show.receive(frame, 0.02); });
}

void test_clock_and_state_validation() {
    auto show = controller();
    rejects([&] { show.pause(0.0); });
    rejects([&] { show.resume(0.0); });
    show.restart(0.0);
    rejects([&] { show.resume(0.1); });
    show.pause(0.1);
    rejects([&] { show.pause(0.2); });
    show.tick(0.5);
    for (double bad : {-1.0, 0.4, std::numeric_limits<double>::infinity(),
                        std::numeric_limits<double>::quiet_NaN()}) {
        rejects([&] { show.tick(bad); });
        rejects([&] { show.set_mode(ShowMode::Touch, bad); });
        rejects([&] { show.pause(bad); });
        rejects([&] { show.resume(bad); });
        rejects([&] { show.restart(bad); });
        rejects([&] { show.reset_input_sequences(bad); });
        rejects([&] { show.receive(body_frame(InputSource::Touch, 1), bad); });
    }
    rejects([&] { show.set_mode(static_cast<ShowMode>(99), 0.5); });
    require(show.paused() && show.mode() == ShowMode::Script, "invalid operation mutated show state");
    rejects([] {
        ShowController invalid(simple_script(), {body_axis()}, {90.0}, nullptr);
    });
}

void test_mapper_hold_does_not_renew_input_or_catchup() {
    MotionMapper mapper({body_axis(10.0)}, {90.0});
    ShadowPose pose;
    pose.at(RodId::WusongNeck) = {1.0, 0.0, true};
    mapper.submit_pose(pose, 0.0);
    near(mapper.step(0.02)[0].angle_deg, 90.2);
    const auto held = mapper.hold(100.0);
    near(held[0].angle_deg, 90.2);
    require(held[0].input_state == InputState::CommandHeld, "hold diagnostic missing");
    const auto expired = mapper.step(100.0);
    near(expired[0].angle_deg, 90.2);
    require(expired[0].input_state == InputState::ReturningToNeutral, "hold renewed input validity");
    near(mapper.step(100.01)[0].angle_deg, 90.1);
    rejects([&] { mapper.hold(99.0); });
}

void test_input_record_replay_roundtrip() {
    auto frame = body_frame(InputSource::Camera, std::numeric_limits<std::uint64_t>::max(), 0.75);
    std::ostringstream stream;
    record_input(stream, 0.125, frame);
    frame.seq = 0;
    frame.points.clear();
    record_input(stream, 1.5, frame);
    TempFile file(stream.str());
    const auto records = load_input_replay(file.path);
    require(records.size() == 2, "record count changed");
    near(records[0].arrival_s, 0.125);
    near(records[1].arrival_s, 1.5);
    require(records[0].frame.seq == std::numeric_limits<std::uint64_t>::max(), "record sequence rounded");
    near(records[0].frame.points.at("neck").x, 0.75);
    require(records[1].frame.points.empty(), "loss frame changed");
    for (double bad : {-1.0, std::numeric_limits<double>::infinity(),
                        std::numeric_limits<double>::quiet_NaN(), std::numeric_limits<double>::max()}) {
        rejects([&] { record_input(stream, bad, frame); });
    }
    std::ostringstream broken;
    broken.setstate(std::ios::badbit);
    rejects([&] { record_input(broken, 0.0, frame); });
}

void test_command_schema_and_application() {
    auto show = controller();
    for (const auto* command : {"script", "touch", "camera", "stop", "pause", "resume",
                                "restart", "reset-inputs", "quit"}) {
        require(valid_command(command), "known command rejected");
    }
    for (const auto* command : {"", "SCRIPT", "stopped", "shell", "script;quit"}) {
        require(!valid_command(command), "unknown command marked valid");
        rejects([&] { apply_command(show, command, 0.0); });
    }
    require(!apply_command(show, "script", 0.0), "script quit unexpectedly");
    apply_command(show, "pause", 0.1);
    require(show.paused(), "pause command failed");
    apply_command(show, "resume", 0.2);
    require(!show.paused(), "resume command failed");
    apply_command(show, "camera", 0.3);
    require(show.mode() == ShowMode::Camera, "camera command failed");
    apply_command(show, "stop", 0.4);
    apply_command(show, "reset-inputs", 0.4);
    require(apply_command(show, "quit", 0.5), "quit flag absent");
    require(show.mode() == ShowMode::Stopped, "quit did not stop");
}

void test_command_schedule() {
    TempFile valid("# comment\n\ntime_ms,command\n0,script\n100,pause\n100,resume\n 200 , stop \n");
    const auto commands = load_command_schedule(valid.path);
    require(commands.size() == 4, "command count wrong");
    near(commands[1].time_s, 0.1);
    require(commands[1].command == "pause" && commands[2].command == "resume",
            "same-time command order changed");
    for (const std::string& text : std::vector<std::string>{
            "", "wrong,header\n0,script\n", "time_ms,command\n0,unknown\n",
            "time_ms,command\n0,script,extra\n", "time_ms,command\n-1,script\n",
            "time_ms,command\nnan,script\n", "time_ms,command\n20,stop\n10,script\n"}) {
        TempFile invalid(text);
        rejects([&] { load_command_schedule(invalid.path); });
    }
}

void test_numeric_options() {
    near(parse_nonnegative_number("0", "test"), 0.0);
    near(parse_nonnegative_number("1.25", "test"), 1.25);
    for (const auto* text : {"", "-1", "nan", "inf", "1x", "1 2", "1e999"}) {
        rejects([&] { parse_nonnegative_number(text, "test"); });
    }
    require(parse_port("1") == 1 && parse_port("65535") == 65535, "valid port rejected");
    for (const auto* text : {"0", "65536", "12.5", "-1", "nan", "100bad"}) {
        rejects([&] { parse_port(text); });
    }
}

const std::string config_text =
    "{\"version\":2,\"confidence_threshold\":0.65,\"min_shoulder_width\":0.08,"
    "\"hand_span_shoulders\":2.5,\"neck_gain_x\":1.5,\"neck_gain_y\":-2,"
    "\"neck_origin_x\":0.5,\"neck_origin_y\":0.68,\"mirror_x\":true}";

std::string replaced(std::string text, const std::string& from, const std::string& to) {
    const auto where = text.find(from);
    require(where != std::string::npos, "bad test replacement");
    text.replace(where, from.size(), to);
    return text;
}

void test_retarget_config_validation() {
    TempFile valid(config_text);
    const auto config = load_retarget_config(valid.path);
    near(config.confidence_threshold, 0.65);
    near(config.hand_span_shoulders, 2.5);
    near(config.neck_gain_y, -2.0);
    near(config.neck_origin_x, 0.5);
    near(config.neck_origin_y, 0.68);
    require(config.mirror_x, "mirror setting lost");
    for (const auto& text : std::vector<std::string>{
            "null", "{}", config_text + "trailing",
            replaced(config_text, "\"version\":2", "\"version\":1"),
            replaced(config_text, "\"version\":2", "\"version\":2.0"),
            replaced(config_text, "\"version\":2", "\"version\":2,\"version\":2"),
            replaced(config_text, "0.65", "1.2"),
            replaced(config_text, "0.08", "0"),
            replaced(config_text, "2.5", "-1"),
            replaced(config_text, "1.5", "\"1.5\""),
            replaced(config_text, "\"neck_origin_x\":0.5", "\"neck_origin_x\":-0.1"),
            replaced(config_text, "\"neck_origin_y\":0.68", "\"neck_origin_y\":1.1"),
            replaced(config_text, "true", "1"),
            replaced(config_text, "neck_gain_y", "typo_gain_y")}) {
        TempFile invalid(text);
        rejects([&] { load_retarget_config(invalid.path); });
    }
}

void test_csv_backend_output_and_io_errors() {
    auto show = controller();
    show.restart(0.0);
    show.tick(0.1);
    show.pause(0.1);
    const auto tick = show.tick(0.2);
    std::ostringstream output;
    CsvMotorBackend backend(output);
    backend.send(tick);
    backend.shutdown();
    const auto csv = output.str();
    require(csv.find("time_s,mode,playback_s,axis_id,rod,angle_deg") == 0, "trace header missing");
    require(csv.find("0.200000,paused,0.100000,body_x,wusong_neck,120.000000") != std::string::npos,
            "trace changed mode, clock, axis or angle");
    require(csv.find("command_held") != std::string::npos, "hold diagnostic absent");
    auto bad_tick = tick;
    bad_tick.time_s = std::numeric_limits<double>::infinity();
    rejects([&] { backend.send(bad_tick); });
    std::ostringstream broken;
    broken.setstate(std::ios::badbit);
    rejects([&] { CsvMotorBackend invalid(broken); });
    output.setstate(std::ios::badbit);
    rejects([&] { backend.send(tick); });
    rejects([&] { backend.shutdown(); });
}

void test_existing_output_is_preserved() {
    TempFile existing("keep this text");
    rejects([&] { require_new_output(existing.path); });
    std::ifstream stream(existing.path);
    std::string text;
    std::getline(stream, text);
    require(text == "keep this text", "existing output was modified");
    require_new_output(existing.path + ".not_created");
}

} // namespace

int main() {
    const std::vector<std::pair<const char*, std::function<void()>>> tests = {
        {"v2 process restart needs explicit reset", test_v2_restart_requires_explicit_reset},
        {"v2 person change needs rearm", test_v2_new_person_stops_until_rearmed},
        {"v2 loss frames and inactive lifecycle", test_v2_loss_frames_and_inactive_session_change},
        {"pause holds command through timeout", test_pause_holds_last_command_through_timeout},
        {"resume has no pause catchup", test_resume_has_no_elapsed_pause_catchup},
        {"script completion and restart", test_script_completion_and_restart},
        {"mode switch discards old targets", test_switch_mode_discards_previous_targets},
        {"active source and independent sequences", test_source_selection_and_independent_sequences},
        {"duplicate does not refresh timeout", test_duplicate_frames_do_not_refresh_timeout},
        {"sequence reset requires stop", test_sequence_reset_requires_stop},
        {"malformed C++ frame cannot poison sequence", test_malformed_cpp_frame_does_not_poison_sequence},
        {"clock and state validation", test_clock_and_state_validation},
        {"mapper hold does not renew input", test_mapper_hold_does_not_renew_input_or_catchup},
        {"record and replay roundtrip", test_input_record_replay_roundtrip},
        {"command schema and application", test_command_schema_and_application},
        {"command schedule", test_command_schedule},
        {"numeric options", test_numeric_options},
        {"retarget configuration", test_retarget_config_validation},
        {"CSV output and IO errors", test_csv_backend_output_and_io_errors},
        {"preserve existing output", test_existing_output_is_preserved}
    };
    int failures = 0;
    for (const auto& test : tests) {
        try { test.second(); std::cout << "PASS " << test.first << '\n'; }
        catch (const std::exception& error) {
            ++failures;
            std::cerr << "FAIL " << test.first << ": " << error.what() << '\n';
        }
    }
    std::cout << tests.size() - failures << '/' << tests.size() << " controller test groups passed\n";
    return failures ? 1 : 0;
}
