#include "shadow/input.hpp"
#include "shadow/runtime_io.hpp"
#include "shadow/udp.hpp"
#include <chrono>
#include <iostream>
#include <stdexcept>
#include <string>
#include <thread>

int main(int argc, char** argv) {
    try {
        std::string file, command;
        bool console = false;
        std::uint16_t port = 0;
        for (int i = 1; i < argc; ++i) {
            const std::string key = argv[i];
            const auto next = [&]() -> std::string {
                if (++i >= argc) throw std::invalid_argument("missing value for " + key);
                return argv[i];
            };
            if (key == "--port") port = shadow::parse_port(next());
            else if (key == "--file") file = next();
            else if (key == "--command") command = next();
            else if (key == "--console") console = true;
            else if (key == "--help") {
                std::cout << "shadow_send --port PORT --file REPLAY.jsonl\n"
                             "shadow_send --port PORT --command camera\n"
                             "shadow_send --port PORT --console\n"
                             "Fixed destination: 127.0.0.1. Run in the SAME OS/network namespace\n"
                             "as shadow_show. Replay uses original timing, sequence and source.\n"
                             "Console commands: script touch camera pause resume restart stop reset-inputs quit\n";
                return 0;
            } else throw std::invalid_argument("unknown option: " + key);
        }
        if (!port || static_cast<int>(!file.empty()) + static_cast<int>(!command.empty()) +
                         static_cast<int>(console) != 1) {
            throw std::invalid_argument("provide --port and exactly one of --file, --command, --console");
        }
        shadow::LoopbackUdp socket;
        if (!command.empty()) {
            if (!shadow::valid_command(command)) throw std::invalid_argument("unknown control command");
            socket.send(command, port);
            std::cout << "Sent command; inspect receiver log/trace for actual state.\n";
        } else if (console) {
            std::cout << "Enter commands, one per line (quit also closes this console):\n";
            while (std::getline(std::cin, command)) {
                if (!shadow::valid_command(command)) {
                    std::cerr << "Unknown command; use script/touch/camera/pause/resume/restart/stop/reset-inputs/quit\n";
                    continue;
                }
                socket.send(command, port);
                if (command == "quit") break;
            }
        } else {
            const auto frames = shadow::load_input_replay(file);
            using Clock = std::chrono::steady_clock;
            const auto start = Clock::now();
            for (const auto& frame : frames) {
                std::this_thread::sleep_until(start + std::chrono::duration_cast<Clock::duration>(
                    std::chrono::duration<double>(frame.arrival_s)));
                socket.send(shadow::serialize_input_frame(frame.frame), port);
            }
            std::cout << "Sent " << frames.size() << " frames; UDP does not acknowledge delivery.\n";
        }
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "Error: " << error.what() << '\n';
        return 1;
    }
}
