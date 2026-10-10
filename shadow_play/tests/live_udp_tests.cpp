#include "shadow/input.hpp"
#include "shadow/runtime_io.hpp"
#include "shadow/udp.hpp"

#include <arpa/inet.h>
#include <cerrno>
#include <chrono>
#include <cmath>
#include <csignal>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <fstream>
#include <iostream>
#include <iterator>
#include <map>
#include <memory>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <sys/socket.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <thread>
#include <unistd.h>
#include <vector>

namespace {
using Clock = std::chrono::steady_clock;
using namespace std::chrono_literals;

void require(bool condition, const std::string& message) {
    if (!condition) throw std::runtime_error(message);
}

std::string read_text(const std::string& path) {
    std::ifstream input(path);
    return {std::istreambuf_iterator<char>(input), std::istreambuf_iterator<char>()};
}

// Hold ephemeral loopback ports until immediately before exec. Retrying startup
// handles the small unavoidable close/bind race without fixed test port numbers.
class PortReservation {
public:
    PortReservation() {
        socket_ = socket(AF_INET, SOCK_DGRAM | SOCK_CLOEXEC, IPPROTO_UDP);
        if (socket_ < 0) throw std::runtime_error("cannot create port reservation socket");
        sockaddr_in address{};
        address.sin_family = AF_INET;
        address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
        address.sin_port = 0;
        if (bind(socket_, reinterpret_cast<const sockaddr*>(&address), sizeof(address)) != 0) {
            close(socket_);
            throw std::runtime_error("cannot reserve a loopback UDP port");
        }
        socklen_t length = sizeof(address);
        if (getsockname(socket_, reinterpret_cast<sockaddr*>(&address), &length) != 0) {
            close(socket_);
            throw std::runtime_error("cannot read reserved UDP port");
        }
        port_ = ntohs(address.sin_port);
    }
    ~PortReservation() { release(); }
    PortReservation(const PortReservation&) = delete;
    PortReservation& operator=(const PortReservation&) = delete;
    std::uint16_t port() const { return port_; }
    void release() {
        if (socket_ >= 0) { close(socket_); socket_ = -1; }
    }
private:
    int socket_ = -1;
    std::uint16_t port_ = 0;
};

class Child {
public:
    Child(const std::vector<std::string>& arguments, const std::string& out,
          const std::string& error) {
        std::vector<char*> argv;
        for (const auto& argument : arguments) argv.push_back(const_cast<char*>(argument.c_str()));
        argv.push_back(nullptr);
        pid_ = fork();
        if (pid_ < 0) throw std::runtime_error("fork failed");
        if (pid_ == 0) {
            // Use only async-signal-safe operations between fork and exec.
            const int stdout_fd = open(out.c_str(), O_WRONLY | O_CREAT | O_EXCL, 0600);
            const int stderr_fd = open(error.c_str(), O_WRONLY | O_CREAT | O_EXCL, 0600);
            if (stdout_fd < 0 || stderr_fd < 0 || dup2(stdout_fd, STDOUT_FILENO) < 0 ||
                dup2(stderr_fd, STDERR_FILENO) < 0) _exit(126);
            close(stdout_fd);
            close(stderr_fd);
            execv(argv[0], argv.data());
            constexpr char message[] = "live_udp_tests: execv failed\n";
            (void)write(STDERR_FILENO, message, sizeof(message) - 1);
            _exit(127);
        }
    }
    ~Child() {
        if (!finished_) {
            (void)kill(pid_, SIGCONT);
            (void)kill(pid_, SIGTERM);
            const auto deadline = Clock::now() + 300ms;
            while (Clock::now() < deadline) {
                const auto result = waitpid(pid_, &status_, WNOHANG);
                if (result == pid_ || (result < 0 && errno == ECHILD)) { finished_ = true; break; }
                std::this_thread::sleep_for(5ms);
            }
            if (!finished_) {
                (void)kill(pid_, SIGKILL);
                while (waitpid(pid_, &status_, 0) < 0 && errno == EINTR) {}
            }
        }
    }
    Child(const Child&) = delete;
    Child& operator=(const Child&) = delete;
    bool poll() {
        if (finished_) return true;
        const auto result = waitpid(pid_, &status_, WNOHANG);
        if (result < 0 && errno != EINTR) throw std::runtime_error("waitpid failed");
        if (result == pid_) finished_ = true;
        return finished_;
    }
    void wait_success(std::chrono::milliseconds timeout) {
        const auto deadline = Clock::now() + timeout;
        while (!poll() && Clock::now() < deadline) std::this_thread::sleep_for(5ms);
        require(poll(), "controller did not exit within the bounded wait");
        require(WIFEXITED(status_) && WEXITSTATUS(status_) == 0, "controller did not exit successfully");
    }
    void suspend_for_batch() {
        require(!poll(), "controller exited before quit regression test");
        require(kill(pid_, SIGSTOP) == 0, "cannot suspend child for command batch");
        const auto deadline = Clock::now() + 500ms;
        while (Clock::now() < deadline) {
            int status = 0;
            const auto result = waitpid(pid_, &status, WNOHANG | WUNTRACED);
            if (result == pid_) {
                if (WIFSTOPPED(status)) return;
                status_ = status;
                finished_ = true;
                throw std::runtime_error("controller exited before suspension");
            }
            if (result < 0 && errno != EINTR) throw std::runtime_error("suspension waitpid failed");
            std::this_thread::sleep_for(2ms);
        }
        throw std::runtime_error("controller did not suspend within the bounded wait");
    }
    void continue_running() { require(kill(pid_, SIGCONT) == 0, "cannot resume suspended child"); }
private:
    pid_t pid_ = -1;
    int status_ = 0;
    bool finished_ = false;
};

void await_log(Child& child, const std::string& path, const std::string& needle,
               std::chrono::milliseconds timeout = 750ms) {
    const auto deadline = Clock::now() + timeout;
    while (Clock::now() < deadline) {
        if (read_text(path).find(needle) != std::string::npos) return;
        if (child.poll()) throw std::runtime_error("controller exited while awaiting log: " + needle);
        std::this_thread::sleep_for(5ms);
    }
    throw std::runtime_error("timed out awaiting log: " + needle);
}

std::size_t counter(const std::string& log, const std::string& name) {
    const auto completed = log.rfind("Completed.");
    require(completed != std::string::npos, "completion counters missing from stderr");
    const auto position = log.find(name + '=', completed);
    require(position != std::string::npos, "missing counter " + name);
    std::size_t used = 0;
    const auto value = std::stoull(log.substr(position + name.size() + 1), &used);
    require(used > 0, "invalid counter " + name);
    return static_cast<std::size_t>(value);
}

std::vector<std::string> cells(const std::string& line) {
    std::vector<std::string> result;
    std::istringstream stream(line);
    std::string cell;
    while (std::getline(stream, cell, ',')) result.push_back(cell);
    return result;
}

void check_trace(const std::string& path) {
    std::ifstream stream(path);
    require(static_cast<bool>(stream), "trace file is missing");
    std::string line;
    require(static_cast<bool>(std::getline(stream, line)), "trace is empty");
    const auto header = cells(line);
    std::map<std::string, std::size_t> columns;
    for (std::size_t i = 0; i < header.size(); ++i) columns.emplace(header[i], i);
    for (const char* name : {"time_s", "mode", "playback_s", "axis_id", "angle_deg", "input_state"}) {
        require(columns.count(name) == 1, std::string("missing trace column ") + name);
    }
    std::set<std::string> modes;
    std::map<std::string, double> previous_time, paused_angle;
    std::size_t paused_rows = 0, rows = 0;
    std::string last_mode;
    double paused_position = -1.0;
    bool moved = false;
    while (std::getline(stream, line)) {
        const auto row = cells(line);
        require(row.size() == header.size(), "malformed trace row");
        const auto field = [&](const std::string& name) -> const std::string& { return row.at(columns.at(name)); };
        const double time = std::stod(field("time_s"));
        const double angle = std::stod(field("angle_deg"));
        const double position = std::stod(field("playback_s"));
        require(std::isfinite(time) && std::isfinite(angle) && std::isfinite(position), "nonfinite trace data");
        const auto& axis = field("axis_id");
        if (previous_time.count(axis)) require(time > previous_time.at(axis), "nonmonotonic per-axis trace time");
        previous_time[axis] = time;
        last_mode = field("mode");
        modes.insert(last_mode);
        if ((last_mode == "touch" || last_mode == "camera") && std::abs(angle - 90.0) > 1.0) moved = true;
        if (last_mode == "paused") {
            ++paused_rows;
            if (paused_position < 0.0) paused_position = position;
            require(std::abs(position - paused_position) < 1e-6, "audio clock advanced during pause");
            if (paused_angle.count(axis)) require(std::abs(angle - paused_angle.at(axis)) < 1e-6, "motor command moved during pause");
            paused_angle[axis] = angle;
            require(field("input_state") == "command_held", "pause did not hold motor commands");
        }
        ++rows;
    }
    require(!stream.bad() && rows > 0, "trace reading failed or contains no samples");
    for (const char* mode : {"touch", "camera", "script", "paused", "stopped"}) require(modes.count(mode) == 1, std::string("mode absent from trace: ") + mode);
    require(moved, "interactive inputs never changed an angle");
    require(paused_rows >= paused_angle.size() * 2, "need at least two paused ticks");
    require(last_mode == "stopped", "quit did not leave the final output stopped");
}

struct Artifacts {
    std::string stdout_file, stderr_file, trace, inputs, commands;
};

void remove_known_artifacts(const Artifacts& files) {
    for (const auto* path : {&files.stdout_file, &files.stderr_file, &files.trace, &files.inputs, &files.commands}) (void)std::remove(path->c_str());
}
} // namespace

int main(int argc, char** argv) {
    if (argc != 3) {
        std::cerr << "Usage: live_udp_tests ABSOLUTE_SHADOW_SHOW ABSOLUTE_SOURCE_DIR\n";
        return 2;
    }
    std::string directory;
    std::string active_log;
    try {
        require(argv[1][0] == '/' && argv[2][0] == '/', "test requires absolute executable and source paths");
        const std::string executable = argv[1];
        const std::string source = argv[2];
        auto touch = shadow::load_input_replay(source + "/assets/touch_demo.jsonl");
        auto camera = shadow::load_input_replay(source + "/assets/camera_demo.jsonl");
        require(touch.size() >= 31 && camera.size() >= 31, "expected 31 touch and camera fixture frames");
        char pattern[] = "/tmp/shadow_live_udp_XXXXXX";
        const auto* temporary = mkdtemp(pattern);
        require(temporary != nullptr, "cannot create unique integration-test directory");
        directory = temporary;

        std::unique_ptr<Child> child;
        std::vector<Artifacts> attempts;
        Artifacts files;
        std::uint16_t input_port = 0, control_port = 0;
        for (unsigned attempt = 0; attempt < 5; ++attempt) {
            PortReservation input, control;
            input_port = input.port();
            control_port = control.port();
            require(input_port != control_port, "reserved UDP ports unexpectedly match");
            const std::string prefix = directory + "/attempt" + std::to_string(attempt);
            files = {prefix + ".stdout", prefix + ".stderr", prefix + ".csv", prefix + ".jsonl", prefix + ".commands.csv"};
            attempts.push_back(files);
            active_log = files.stderr_file;
            const std::vector<std::string> arguments = {
                executable, "--mode", "touch", "--realtime", "--seconds", "3",
                "--listen", std::to_string(input_port), "--control-port", std::to_string(control_port),
                "--script", source + "/assets/rehearsal90.json",
                "--calibration", source + "/config/calibration.simulation.csv",
                "--retarget", source + "/config/retarget.simulation.json",
                "--output", files.trace, "--record-input", files.inputs,
                "--record-commands", files.commands
            };
            input.release();
            control.release();
            child = std::make_unique<Child>(arguments, files.stdout_file, files.stderr_file);
            try {
                await_log(*child, files.stderr_file, "Input UDP: 127.0.0.1:" + std::to_string(input_port), 1500ms);
                await_log(*child, files.stderr_file, "Control UDP: 127.0.0.1:" + std::to_string(control_port));
                break;
            } catch (...) {
                const bool bind_race = read_text(files.stderr_file).find("bind 127.0.0.1") != std::string::npos;
                if (!bind_race || attempt == 4) throw;
                child.reset();
            }
        }
        require(static_cast<bool>(child), "no running controller after port retries");
        shadow::LoopbackUdp sender;
        auto inactive_camera = camera.front().frame;
        inactive_camera.seq = 0;
        sender.send(shadow::serialize_input_frame(inactive_camera), input_port);
        for (std::size_t i = 0; i < 31; ++i) {
            sender.send(shadow::serialize_input_frame(touch[i].frame), input_port);
            std::this_thread::sleep_for(10ms);
        }
        sender.send(shadow::serialize_input_frame(touch[30].frame), input_port); // Duplicate.
        sender.send(shadow::serialize_input_frame(touch.front().frame), input_port); // Old sequence.
        sender.send("{malformed-json", input_port);
        std::this_thread::sleep_for(150ms);

        sender.send("camera", control_port);
        await_log(*child, files.stderr_file, "Command camera -> camera");
        for (std::size_t i = 0; i < 31; ++i) {
            sender.send(shadow::serialize_input_frame(camera[i].frame), input_port);
            std::this_thread::sleep_for(10ms);
        }
        std::this_thread::sleep_for(150ms);
        sender.send("script", control_port);
        await_log(*child, files.stderr_file, "Command script -> script");
        std::this_thread::sleep_for(100ms);
        sender.send("pause", control_port);
        await_log(*child, files.stderr_file, "Command pause -> script (paused)");
        std::this_thread::sleep_for(120ms);
        sender.send("resume", control_port);
        await_log(*child, files.stderr_file, "Command resume -> script");
        std::this_thread::sleep_for(100ms);

        // Queue both packets while the child is stopped so the regression check
        // exercises one receive batch instead of depending on scheduler luck.
        child->suspend_for_batch();
        sender.send("quit", control_port);
        sender.send("script", control_port);
        child->continue_running();
        child->wait_success(1500ms);
        const auto log = read_text(files.stderr_file);
        require(counter(log, "accepted") == 62, "expected all 62 active frames to be accepted");
        require(counter(log, "inactive") == 1, "inactive source was not counted");
        require(counter(log, "duplicate/old") == 2, "duplicate/old sequences were not discarded");
        require(counter(log, "malformed") == 1, "malformed JSON was not discarded");
        require(counter(log, "oversize") == 0, "unexpected oversized packet count");
        const auto quit_position = log.find("Command quit -> stopped");
        require(quit_position != std::string::npos, "quit acknowledgment is missing");
        require(log.find("Command script", quit_position) == std::string::npos, "script was applied after quit in the same batch");

        const auto recording = shadow::load_input_replay(files.inputs);
        require(recording.size() == 65, "valid input recording lost frames or recorded malformed JSON");
        std::size_t recorded_touch = 0, recorded_camera = 0;
        for (const auto& record : recording) {
            if (record.frame.source == shadow::InputSource::Touch) ++recorded_touch;
            else if (record.frame.source == shadow::InputSource::Camera) ++recorded_camera;
        }
        require(recorded_touch == 33 && recorded_camera == 32, "recorded sources/duplicates do not match the sent stream");
        const auto controls = shadow::load_command_schedule(files.commands);
        const std::vector<std::string> expected = {"touch", "camera", "script", "pause", "resume", "quit"};
        require(controls.size() == expected.size(), "accepted command recording has unexpected entries");
        for (std::size_t i = 0; i < expected.size(); ++i) require(controls[i].command == expected[i], "command recording order is incorrect");
        check_trace(files.trace);
        require(read_text(files.stdout_file).empty(), "CSV output leaked to stdout despite --output");
        child.reset();
        for (const auto& attempt : attempts) remove_known_artifacts(attempt);
        (void)rmdir(directory.c_str());
        std::cout << "PASS live UDP CLI: 62 accepted, 1 inactive, 2 duplicate/old, 1 malformed; "
                     "recording, mode changes, pause hold and quit batch verified.\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "FAIL live UDP CLI: " << error.what() << '\n';
        if (!directory.empty()) std::cerr << "Artifacts retained: " << directory << '\n';
        if (!active_log.empty()) std::cerr << read_text(active_log);
        return 1;
    }
}
