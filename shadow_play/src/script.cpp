#include "shadow/script.hpp"

#include <nlohmann/json.hpp>

#include <algorithm>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <set>
#include <stdexcept>

namespace shadow {
namespace {

double finite_number(const nlohmann::json& value, const std::string& name) {
    if (!value.is_number()) throw std::runtime_error(name + " must be a number");
    const auto result = value.get<double>();
    if (!std::isfinite(result)) throw std::runtime_error(name + " must be finite");
    return result;
}

}  // namespace

Script load_script_json(const std::string& path) {
    try {
        std::ifstream input(path);
        if (!input) throw std::runtime_error("cannot open file");
        std::vector<std::set<std::string>> object_keys;
        const auto reject_duplicates = [&object_keys](int, nlohmann::json::parse_event_t event,
                                                      nlohmann::json& parsed) {
            if (event == nlohmann::json::parse_event_t::object_start) {
                object_keys.emplace_back();
            } else if (event == nlohmann::json::parse_event_t::object_end) {
                object_keys.pop_back();
            } else if (event == nlohmann::json::parse_event_t::key) {
                const auto key = parsed.get<std::string>();
                if (!object_keys.back().insert(key).second) {
                    throw std::runtime_error("duplicate JSON key: " + key);
                }
            }
            return true;
        };
        const auto document = nlohmann::json::parse(input, reject_duplicates);
        if (!document.is_object()) throw std::runtime_error("root must be an object");
        const std::set<std::string> allowed_root{
            "version", "title", "notes", "duration_ms", "audio_file", "interpolation", "frames"};
        for (auto item = document.begin(); item != document.end(); ++item) {
            if (allowed_root.count(item.key()) == 0) {
                throw std::runtime_error("unknown script field: " + item.key());
            }
        }
        for (const char* field : {"title", "notes"}) {
            if (document.contains(field) && !document.at(field).is_string()) {
                throw std::runtime_error(std::string(field) + " must be a string");
            }
        }
        if (!document.at("version").is_number_integer() ||
            document.at("version") != 1) {
            throw std::runtime_error("version must be integer 1");
        }
        Script script;
        if (document.contains("interpolation")) {
            const auto& mode = document.at("interpolation");
            if (!mode.is_string() || (mode != "linear" && mode != "quintic")) {
                throw std::runtime_error("interpolation must be linear or quintic");
            }
            if (mode == "quintic") script.interpolation = Script::Interpolation::Quintic;
        }
        const double duration_ms = finite_number(document.at("duration_ms"), "duration_ms");
        if (duration_ms <= 0.0 || duration_ms > 24.0 * 3600.0 * 1000.0) {
            throw std::runtime_error("duration_ms must be positive and at most 24 hours");
        }
        script.duration_s = duration_ms / 1000.0;
        if (document.contains("audio_file")) {
            const auto name = document.at("audio_file").get<std::string>();
            if (!name.empty()) {
                script.audio_file = std::filesystem::absolute(
                    std::filesystem::path(path).parent_path() / name).lexically_normal().string();
            }
        }
        const auto& frames = document.at("frames");
        if (!frames.is_array() || frames.size() < 2 || frames.size() > 100000) {
            throw std::runtime_error("frames must contain 2..100000 entries");
        }
        double previous_ms = -1.0;
        for (const auto& item : frames) {
            if (!item.is_object() || item.size() != 2 ||
                !item.contains("time_ms") || !item.contains("rods")) {
                throw std::runtime_error("frame fields must be exactly time_ms and rods");
            }
            const double time_ms = finite_number(item.at("time_ms"), "frame time_ms");
            if (time_ms < 0.0 || time_ms > duration_ms || time_ms <= previous_ms) {
                throw std::runtime_error("frame times must strictly increase within the duration");
            }
            ScriptKeyframe frame;
            frame.time_s = time_ms / 1000.0;
            const auto& rods = item.at("rods");
            if (!rods.is_object() || rods.size() != kRodCount) {
                throw std::runtime_error("each frame requires exactly five named rods");
            }
            std::array<bool, kRodCount> seen{};
            for (auto entry = rods.begin(); entry != rods.end(); ++entry) {
                const auto rod = parse_rod_name(entry.key());
                const auto index = static_cast<std::size_t>(rod);
                if (seen[index]) throw std::runtime_error("duplicate rod alias: " + entry.key());
                seen[index] = true;
                const auto& point = entry.value();
                if (!point.is_array() || point.size() != 2) {
                    throw std::runtime_error(std::string(rod_name(rod)) + " must be [x,y]");
                }
                const double x = finite_number(point[0], "rod x");
                const double y = finite_number(point[1], "rod y");
                if (std::abs(x) > 1.0 || std::abs(y) > 1.0) {
                    throw std::runtime_error("rod coordinates must be in [-1,1]");
                }
                frame.pose.at(rod) = {x, y, true};
            }
            script.frames.push_back(frame);
            previous_ms = time_ms;
        }
        if (script.frames.front().time_s != 0.0 || previous_ms != duration_ms) {
            throw std::runtime_error("first frame must be at zero and last frame at duration_ms");
        }
        return script;
    } catch (const std::exception& error) {
        throw std::runtime_error("Script '" + path + "': " + error.what());
    }
}

ShadowPose Script::sample(double time_s) const {
    if (!std::isfinite(time_s)) throw std::invalid_argument("script sample time must be finite");
    if (frames.size() < 2 || !(duration_s > 0.0)) {
        throw std::logic_error("cannot sample an uninitialized script");
    }
    if (time_s <= frames.front().time_s) return frames.front().pose;
    if (time_s >= frames.back().time_s) return frames.back().pose;
    const auto after = std::upper_bound(frames.begin(), frames.end(), time_s,
        [](double time, const ScriptKeyframe& frame) { return time < frame.time_s; });
    const auto& before = *(after - 1);
    double fraction = (time_s - before.time_s) / (after->time_s - before.time_s);
    if (interpolation == Interpolation::Quintic) {
        fraction = fraction * fraction * fraction * (10.0 + fraction * (-15.0 + 6.0 * fraction));
    }
    ShadowPose result;
    for (std::size_t i = 0; i < kRodCount; ++i) {
        const auto& a = before.pose.rods[i];
        const auto& b = after->pose.rods[i];
        result.rods[i] = {a.x + fraction * (b.x - a.x),
                          a.y + fraction * (b.y - a.y), a.valid && b.valid};
    }
    return result;
}

}  // namespace shadow
