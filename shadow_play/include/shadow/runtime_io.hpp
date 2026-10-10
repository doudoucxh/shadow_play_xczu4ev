#pragma once
#include "shadow/controller.hpp"
#include "shadow/input.hpp"
#include <cstdint>
#include <iosfwd>
#include <string>
#include <vector>

namespace shadow {
struct ScheduledCommand { double time_s = 0.0; std::string command; };
double parse_nonnegative_number(const std::string& text, const std::string& label);
std::uint16_t parse_port(const std::string& text);
bool valid_command(const std::string& command);
// Returns true for quit; all other commands are applied to the controller.
bool apply_command(ShowController& controller, const std::string& command, double now_s);
std::vector<ScheduledCommand> load_command_schedule(const std::string& path);
RetargetConfig load_retarget_config(const std::string& path);
void record_input(std::ostream& stream, double arrival_s, const InputFrame& frame);
// Refuse overwriting an existing file; stdout redirection is also supported by CLI.
void require_new_output(const std::string& path);
} // namespace shadow
