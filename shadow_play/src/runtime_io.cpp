#include "shadow/runtime_io.hpp"
#include <nlohmann/json.hpp>
#include <cmath>
#include <fstream>
#include <set>
#include <stdexcept>

namespace shadow {
namespace {
std::string trim(const std::string& text) {
    const auto first = text.find_first_not_of(" \t\r\n");
    if (first == std::string::npos) return {};
    return text.substr(first, text.find_last_not_of(" \t\r\n") - first + 1);
}
}
double parse_nonnegative_number(const std::string& text, const std::string& label) {
    std::size_t used = 0;
    double value;
    try { value = std::stod(text, &used); }
    catch (const std::exception&) { throw std::invalid_argument("invalid " + label + ": " + text); }
    if (used != text.size() || !std::isfinite(value) || value < 0.0) {
        throw std::invalid_argument(label + " must be finite and nonnegative");
    }
    return value;
}
std::uint16_t parse_port(const std::string& text) {
    const auto port = parse_nonnegative_number(text, "port");
    if (port < 1.0 || port > 65535.0 || std::floor(port) != port) {
        throw std::invalid_argument("port must be an integer from 1 to 65535");
    }
    return static_cast<std::uint16_t>(port);
}
bool valid_command(const std::string& command) {
    const std::set<std::string> commands = {
        "script", "touch", "camera", "stop", "pause", "resume", "restart", "reset-inputs", "quit"
    };
    return commands.count(command) != 0;
}
bool apply_command(ShowController& controller, const std::string& command, double now_s) {
    if (command == "pause") controller.pause(now_s);
    else if (command == "resume") controller.resume(now_s);
    else if (command == "restart") controller.restart(now_s);
    else if (command == "reset-inputs") controller.reset_input_sequences(now_s);
    else if (command == "quit") { controller.set_mode(ShowMode::Stopped, now_s); return true; }
    else if (command == "script" || command == "touch" || command == "camera" || command == "stop") {
        controller.set_mode(parse_show_mode(command), now_s);
    } else throw std::invalid_argument("unknown command: " + command);
    return false;
}
std::vector<ScheduledCommand> load_command_schedule(const std::string& path) {
    std::ifstream input(path);
    if (!input) throw std::runtime_error("cannot open commands: " + path);
    std::vector<ScheduledCommand> output;
    std::string line;
    std::size_t line_number = 0;
    bool header = false;
    while (std::getline(input, line)) {
        ++line_number;
        line = trim(line);
        if (line.empty() || line[0] == '#') continue;
        if (!header) {
            if (line != "time_ms,command") throw std::invalid_argument("commands header must be time_ms,command");
            header = true;
            continue;
        }
        try {
            const auto comma = line.find(',');
            if (comma == std::string::npos || line.find(',', comma + 1) != std::string::npos) {
                throw std::invalid_argument("expected two columns");
            }
            const double time = parse_nonnegative_number(trim(line.substr(0, comma)), "command time") / 1000.0;
            const auto command = trim(line.substr(comma + 1));
            if (!valid_command(command)) throw std::invalid_argument("unknown command");
            if (!output.empty() && time < output.back().time_s) throw std::invalid_argument("times are not sorted");
            output.push_back({time, command});
        } catch (const std::exception& error) {
            throw std::invalid_argument("commands line " + std::to_string(line_number) + ": " + error.what());
        }
    }
    if (!header || input.bad()) throw std::runtime_error("invalid/failed commands input");
    return output;
}
RetargetConfig load_retarget_config(const std::string& path) {
    std::ifstream input(path);
    if (!input) throw std::runtime_error("cannot open retarget config: " + path);
    using Json = nlohmann::json;
    std::vector<std::set<std::string>> keys;
    auto callback = [&](int, Json::parse_event_t event, Json& parsed) {
        if (event == Json::parse_event_t::object_start) keys.emplace_back();
        else if (event == Json::parse_event_t::key) {
            if (!keys.back().insert(parsed.get<std::string>()).second) {
                throw std::invalid_argument("duplicate retarget config key");
            }
        } else if (event == Json::parse_event_t::object_end) keys.pop_back();
        return true;
    };
    const auto json = Json::parse(input, callback);
    const std::set<std::string> allowed = {
        "version", "confidence_threshold", "min_shoulder_width", "hand_span_shoulders",
        "neck_gain_x", "neck_gain_y", "mirror_x", "neck_origin_x", "neck_origin_y"
    };
    if (!json.is_object() || json.size() != allowed.size()) throw std::invalid_argument("invalid retarget fields");
    for (auto it = json.begin(); it != json.end(); ++it) {
        if (!allowed.count(it.key())) throw std::invalid_argument("unknown retarget field: " + it.key());
    }
    if (!json.at("version").is_number_integer() || json.at("version") != 2 ||
        !json.at("mirror_x").is_boolean()) throw std::invalid_argument("retarget config requires version 2, neck_* fields and boolean mirror_x");
    const auto get_number = [&](const char* key) {
        if (!json.at(key).is_number()) throw std::invalid_argument(std::string("not a number: ") + key);
        const double value = json.at(key).get<double>();
        if (!std::isfinite(value)) throw std::invalid_argument("nonfinite retarget parameter");
        return value;
    };
    RetargetConfig config;
    config.confidence_threshold = get_number("confidence_threshold");
    config.min_shoulder_width = get_number("min_shoulder_width");
    config.hand_span_shoulders = get_number("hand_span_shoulders");
    config.neck_gain_x = get_number("neck_gain_x");
    config.neck_gain_y = get_number("neck_gain_y");
    config.neck_origin_x = get_number("neck_origin_x");
    config.neck_origin_y = get_number("neck_origin_y");
    config.mirror_x = json.at("mirror_x").get<bool>();
    Retargeter validated(config);
    (void)validated;
    return config;
}
void record_input(std::ostream& stream, double arrival_s, const InputFrame& frame) {
    if (!std::isfinite(arrival_s) || arrival_s < 0.0 || !std::isfinite(arrival_s * 1000.0)) {
        throw std::invalid_argument("bad recording time");
    }
    nlohmann::json record = {{"arrival_ms", arrival_s * 1000.0},
                             {"frame", nlohmann::json::parse(serialize_input_frame(frame))}};
    stream << record.dump() << '\n';
    if (!stream) throw std::runtime_error("input recording write failed");
}
void require_new_output(const std::string& path) {
    std::ifstream existing(path, std::ios::binary);
    if (existing.good()) throw std::runtime_error("output already exists; choose a new filename: " + path);
}
} // namespace shadow
