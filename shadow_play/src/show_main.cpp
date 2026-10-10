#include "shadow/audio.hpp"
#include "shadow/calibration_csv.hpp"
#include "shadow/controller.hpp"
#include "shadow/motor_backend.hpp"
#include "shadow/runtime_io.hpp"
#include "shadow/udp.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <csignal>
#include <fstream>
#include <iostream>
#include <iomanip>
#include <limits>
#include <memory>
#include <stdexcept>
#include <string>
#include <thread>
#include <utility>
#include <vector>

namespace {
volatile std::sig_atomic_t interrupted = 0;
void on_signal(int) { interrupted = 1; }
struct Options {
    std::string calibration = "config/calibration.simulation.csv";
    std::string script = "assets/rehearsal90.json";
    std::string retarget = "config/retarget.simulation.json";
    std::string commands, output, record, record_commands, wav;
    std::string audio = "clock", audio_device = "default", motor_format = "csv";
    shadow::ShowMode mode = shadow::ShowMode::Script;
    double seconds = 92.0, period_s = 0.02;
    bool realtime = false;
    std::uint16_t input_port = 0, control_port = 0;
    std::vector<std::pair<std::string, double>> replays;
};
void usage() {
    std::cout <<
        "shadow_show --output NEW.csv [options]\n"
        "  --script FILE         version-1 script JSON (default assets/rehearsal90.json)\n"
        "  --calibration FILE    per-axis CSV (default simulation config)\n"
        "  --retarget FILE       skeleton-to-rod settings JSON\n"
        "  --mode MODE           script | touch | camera | stopped\n"
        "  --seconds N           session length (default 92; max 86400)\n"
        "  --period-ms N         control period 1..100 ms (default 20)\n"
        "  --commands FILE       timed command CSV\n"
        "  --replay FILE         recorded JSONL input; repeatable\n"
        "  --replay-at MS FILE   replay with local session offset; repeatable\n"
        "  --record-input FILE   write received valid frames to a new JSONL file\n"
        "  --record-commands FILE record accepted controls for full-session replay\n"
        "  --realtime            use wall time instead of fast simulation\n"
        "  --listen PORT         loopback UDP JSON input; requires --realtime\n"
        "  --control-port PORT   loopback UDP control commands; requires --realtime\n"
        "  --audio clock|device  clock is silent; device is optional Linux ALSA PCM16 WAV\n"
        "  --wav FILE            WAV override (otherwise script audio_file)\n"
        "  --audio-device NAME   ALSA device name (default: default)\n"
        "  --motor-format FMT    csv (default) | jsonl (grouped final motor targets)\n"
        "  --output FILE         new output file; omitted or '-' writes stdout\n"
        "Commands: script touch camera stop pause resume restart reset-inputs quit\n"
        "MOTOR OUTPUT IS SIMULATION ONLY. No PWM or physical hardware writes.\n";
}
Options parse_options(int argc, char** argv) {
    Options result;
    for (int i = 1; i < argc; ++i) {
        const std::string key = argv[i];
        const auto next = [&]() -> std::string {
            if (++i >= argc) throw std::invalid_argument("missing value for " + key);
            return argv[i];
        };
        if (key == "--script") result.script = next();
        else if (key == "--calibration") result.calibration = next();
        else if (key == "--retarget") result.retarget = next();
        else if (key == "--commands") result.commands = next();
        else if (key == "--output") result.output = next();
        else if (key == "--motor-format") result.motor_format = next();
        else if (key == "--record-input") result.record = next();
        else if (key == "--record-commands") result.record_commands = next();
        else if (key == "--wav") result.wav = next();
        else if (key == "--audio") result.audio = next();
        else if (key == "--audio-device") result.audio_device = next();
        else if (key == "--mode") result.mode = shadow::parse_show_mode(next());
        else if (key == "--seconds") result.seconds = shadow::parse_nonnegative_number(next(), "duration");
        else if (key == "--period-ms") result.period_s = shadow::parse_nonnegative_number(next(), "period") / 1000.0;
        else if (key == "--listen") result.input_port = shadow::parse_port(next());
        else if (key == "--control-port") result.control_port = shadow::parse_port(next());
        else if (key == "--realtime") result.realtime = true;
        else if (key == "--replay") result.replays.emplace_back(next(), 0.0);
        else if (key == "--replay-at") {
            const double offset = shadow::parse_nonnegative_number(next(), "replay offset") / 1000.0;
            result.replays.emplace_back(next(), offset);
        } else throw std::invalid_argument("unknown option: " + key);
    }
    if (result.seconds <= 0 || result.seconds > 86400 || result.period_s < 0.001 || result.period_s > 0.1) {
        throw std::invalid_argument("invalid duration or period");
    }
    if (result.audio != "clock" && result.audio != "device") throw std::invalid_argument("audio must be clock or device");
    if (result.motor_format != "csv" && result.motor_format != "jsonl") {
        throw std::invalid_argument("motor-format must be csv or jsonl");
    }
    if (!result.realtime && (result.input_port || result.control_port || result.audio == "device")) {
        throw std::invalid_argument("UDP or actual audio requires --realtime");
    }
    if (result.input_port != 0 && result.input_port == result.control_port) {
        throw std::invalid_argument("input and control ports must differ");
    }
    if ((!result.record.empty() && result.record == result.output) ||
        (!result.record_commands.empty() && (result.record_commands == result.output ||
                                             result.record_commands == result.record))) {
        throw std::invalid_argument("trace, input recording and command recording paths must differ");
    }
    return result;
}
} // namespace

int main(int argc, char** argv) {
    if (argc == 2 && std::string(argv[1]) == "--help") { usage(); return 0; }
    try {
        const auto options = parse_options(argc, argv);
        const auto axes = shadow::load_calibration_csv(options.calibration);
        const auto script = shadow::load_script_json(options.script);
        const auto retarget = shadow::load_retarget_config(options.retarget);
        auto commands = options.commands.empty() ? std::vector<shadow::ScheduledCommand>{}
                                                 : shadow::load_command_schedule(options.commands);
        std::vector<shadow::RecordedInput> frames;
        for (const auto& replay : options.replays) {
            auto source = shadow::load_input_replay(replay.first);
            for (auto& frame : source) {
                frame.arrival_s += replay.second;
                if (!std::isfinite(frame.arrival_s)) throw std::invalid_argument("replay time overflow");
                frames.push_back(std::move(frame));
            }
        }
        std::stable_sort(frames.begin(), frames.end(), [](const auto& a, const auto& b) {
            return a.arrival_s < b.arrival_s;
        });

        std::unique_ptr<shadow::AudioPlayer> audio;
        if (options.audio == "device") {
            const auto wav = options.wav.empty() ? script.audio_file : options.wav;
            if (wav.empty()) throw std::invalid_argument("device audio requires --wav or script audio_file");
            const auto info = shadow::inspect_wav(wav);
            if (std::abs(info.duration_s - script.duration_s) > 0.001) {
                throw std::invalid_argument("WAV and script duration must agree within 1 ms");
            }
            audio = shadow::make_wav_audio(wav, options.audio_device);
        } else {
            if (!options.wav.empty()) throw std::invalid_argument("--wav requires --audio device (clock is silent)");
            audio = shadow::make_clock_audio(script.duration_s);
        }

        std::vector<double> initial;
        for (const auto& axis : axes) initial.push_back(axis.neutral_deg);
        // This explicit neutral assumption is valid ONLY for this mock backend.
        shadow::ShowController controller(script, axes, initial, std::move(audio), retarget);
        std::unique_ptr<shadow::LoopbackUdp> input_udp, control_udp;
        if (options.input_port) input_udp.reset(new shadow::LoopbackUdp(options.input_port));
        if (options.control_port) control_udp.reset(new shadow::LoopbackUdp(options.control_port));

        std::ofstream trace_file, record_file, command_file;
        std::ostream* trace = &std::cout;
        if (!options.output.empty() && options.output != "-") {
            shadow::require_new_output(options.output);
            trace_file.open(options.output);
            if (!trace_file) throw std::runtime_error("cannot create trace; parent directory must exist");
            trace = &trace_file;
        }
        if (!options.record.empty()) {
            shadow::require_new_output(options.record);
            record_file.open(options.record);
            if (!record_file) throw std::runtime_error("cannot create input recording");
        }
        if (!options.record_commands.empty()) {
            shadow::require_new_output(options.record_commands);
            command_file.open(options.record_commands);
            if (!command_file) throw std::runtime_error("cannot create command recording");
            command_file << "time_ms,command\n0," <<
                (options.mode == shadow::ShowMode::Stopped ? "stop" : shadow::show_mode_name(options.mode)) << '\n';
        }
        std::unique_ptr<shadow::MotorBackend> motors;
        if (options.motor_format == "jsonl") motors = std::make_unique<shadow::JsonlMotorBackend>(*trace);
        else motors = std::make_unique<shadow::CsvMotorBackend>(*trace);
        std::signal(SIGINT, on_signal);
        std::signal(SIGTERM, on_signal);
        using Clock = std::chrono::steady_clock;
        const auto origin = Clock::now();
        controller.set_mode(options.mode, 0.0);
        std::cerr << "SIMULATED MOTORS; " << (options.audio == "clock" ? "silent clock" : "ALSA audio")
                  << "; session=" << options.seconds << " s\n";
        if (input_udp) std::cerr << "Input UDP: 127.0.0.1:" << options.input_port << '\n';
        if (control_udp) std::cerr << "Control UDP: 127.0.0.1:" << options.control_port << '\n';

        std::size_t command_index = 0, frame_index = 0, ticks = 0;
        std::size_t accepted = 0, inactive = 0, duplicates = 0, malformed = 0;
        std::size_t lifecycle_rejections = 0;
        bool quit = false;
        double last_now = 0.0;
        const auto control = [&](const std::string& command, double time) {
            const bool exit_requested = shadow::apply_command(controller, command, time);
            if (command_file.is_open()) {
                command_file << std::setprecision(17) << time * 1000.0 << ',' << command << '\n';
                if (!command_file) throw std::runtime_error("command recording write failed");
            }
            return exit_requested;
        };
        const auto deliver = [&](const shadow::InputFrame& frame, double time) {
            if (record_file.is_open()) shadow::record_input(record_file, time, frame);
            switch (controller.receive(frame, time)) {
                case shadow::ReceiveResult::Accepted: ++accepted; break;
                case shadow::ReceiveResult::InactiveSource: ++inactive; break;
                case shadow::ReceiveResult::DuplicateOrOld: ++duplicates; break;
                case shadow::ReceiveResult::InputResetRequired:
                    if (++lifecycle_rejections <= 5) {
                        std::cerr << "Producer session/protocol changed: stop -> reset-inputs -> camera before accepting it.\n";
                    }
                    break;
                case shadow::ReceiveResult::TrackingChanged:
                    ++lifecycle_rejections;
                    std::cerr << "Camera target changed: stopped; send camera to follow the new target.\n";
                    break;
            }
        };
        const auto count_bad = [&](const std::exception& error) {
            if (++malformed <= 5) std::cerr << "Rejected live message: " << error.what() << '\n';
        };
        while (!quit && !interrupted) {
            const double scheduled = std::min(static_cast<double>(ticks) * options.period_s, options.seconds);
            if (options.realtime) std::this_thread::sleep_until(origin + std::chrono::duration_cast<Clock::duration>(
                std::chrono::duration<double>(scheduled)));
            const double now = options.realtime ? std::chrono::duration<double>(Clock::now() - origin).count() : scheduled;
            last_now = now;
            // Merge commands and replay frames chronologically, including events
            // between ticks. Commands win ties to define the mode of that frame.
            while (!quit) {
                const double next_command = command_index < commands.size() ? commands[command_index].time_s
                                                                             : std::numeric_limits<double>::infinity();
                const double next_frame = frame_index < frames.size() ? frames[frame_index].arrival_s
                                                                       : std::numeric_limits<double>::infinity();
                const double event = std::min(next_command, next_frame);
                if (event > now + 1e-9) break;
                // Replay events are received at this control tick, like live
                // packets. Tiny decimal-to-binary errors cannot delay a whole tick.
                const double arrival = now;
                if (next_command <= next_frame + 1e-9) {
                    quit = control(commands[command_index++].command, arrival);
                } else {
                    deliver(frames[frame_index++].frame, arrival);
                }
            }
            // Control commands precede new frame delivery, matching offline
            // replay. A live control transition discards queued old coordinates.
            if (!quit && control_udp) {
                for (const auto& command : control_udp->receive()) {
                    try {
                        quit = control(command, now);
                        if (input_udp) (void)input_udp->receive(4096);
                        std::cerr << "Command " << command << " -> " << shadow::show_mode_name(controller.mode())
                                  << (controller.paused() ? " (paused)" : "") << '\n';
                    }
                    catch (const std::logic_error& error) { count_bad(error); }
                    if (quit) break;
                }
            }
            if (!quit && input_udp) {
                for (const auto& message : input_udp->receive()) {
                    try { deliver(shadow::parse_input_frame(message), now); }
                    catch (const std::invalid_argument& error) { count_bad(error); }
                }
            }
            motors->send(controller.tick(now));
            ++ticks;
            if (now >= options.seconds) break;
            if (options.realtime) {
                // A delayed Linux thread skips obsolete ticks instead of running
                // a burst of updates to catch up. Mapper also caps angle steps.
                const auto next_due = static_cast<std::size_t>(std::floor(now / options.period_s)) + 1;
                ticks = std::max(ticks, next_due);
            }
        }
        controller.set_mode(shadow::ShowMode::Stopped, last_now);
        motors->shutdown();
        if (record_file.is_open()) {
            record_file.flush();
            if (!record_file) throw std::runtime_error("cannot flush recording");
        }
        if (command_file.is_open()) {
            command_file.flush();
            if (!command_file) throw std::runtime_error("cannot flush command recording");
        }
        std::cerr << "Completed. accepted=" << accepted << " inactive=" << inactive
                  << " duplicate/old=" << duplicates << " malformed=" << malformed
                  << " lifecycle_rejections=" << lifecycle_rejections;
        if (input_udp) std::cerr << " oversize=" << input_udp->oversized_dropped();
        std::cerr << '\n';
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "Error: " << error.what() << '\n';
        return 1;
    }
}
