#include "shadow/input.hpp"

#include <nlohmann/json.hpp>

#include <algorithm>
#include <cmath>
#include <fstream>
#include <initializer_list>
#include <set>
#include <stdexcept>
#include <utility>

namespace shadow {
namespace {
using Json = nlohmann::json;
constexpr std::size_t kMaxJsonLineBytes = 65536;

Json strict_json(const std::string& text) {
    if (text.size() > kMaxJsonLineBytes) {
        throw std::invalid_argument("input JSON line exceeds 65536 bytes");
    }
    std::vector<std::set<std::string>> object_keys;
    auto callback = [&](int depth, Json::parse_event_t event, Json& parsed) {
        if (depth > 16) throw std::invalid_argument("input JSON nesting exceeds 16 levels");
        if (event == Json::parse_event_t::object_start) {
            object_keys.emplace_back();
        } else if (event == Json::parse_event_t::key) {
            if (!object_keys.back().insert(parsed.get<std::string>()).second) {
                throw std::invalid_argument("duplicate JSON key: " + parsed.get<std::string>());
            }
        } else if (event == Json::parse_event_t::object_end) {
            object_keys.pop_back();
        }
        return true;
    };
    try {
        return Json::parse(text, callback);
    } catch (const Json::exception& error) {
        throw std::invalid_argument(std::string("invalid input JSON: ") + error.what());
    }
}

void fields(const Json& object, std::initializer_list<const char*> required,
            std::initializer_list<const char*> optional = {}) {
    if (!object.is_object()) throw std::invalid_argument("expected JSON object");
    std::set<std::string> allowed;
    for (const char* key : required) {
        allowed.insert(key);
        if (!object.contains(key)) throw std::invalid_argument(std::string("missing field: ") + key);
    }
    for (const char* key : optional) allowed.insert(key);
    for (auto it = object.begin(); it != object.end(); ++it) {
        if (allowed.count(it.key()) == 0) throw std::invalid_argument("unknown field: " + it.key());
    }
}

std::uint64_t unsigned_integer(const Json& value, const char* name) {
    if (value.is_number_unsigned()) return value.get<std::uint64_t>();
    if (value.is_number_integer() && value.get<std::int64_t>() >= 0) {
        return static_cast<std::uint64_t>(value.get<std::int64_t>());
    }
    throw std::invalid_argument(std::string(name) + " must be an unsigned integer");
}

double finite_number(const Json& value, const char* name) {
    if (!value.is_number()) throw std::invalid_argument(std::string(name) + " must be numeric");
    const double number = value.get<double>();
    if (!std::isfinite(number)) throw std::invalid_argument(std::string(name) + " must be finite");
    return number;
}

double unit_number(const Json& value, const char* name) {
    const double number = finite_number(value, name);
    if (number < 0.0 || number > 1.0) {
        throw std::invalid_argument(std::string(name) + " must be in [0,1]");
    }
    return number;
}

bool valid_session_id(const std::string& value) {
    return !value.empty() && value.size() <= 64 &&
           std::all_of(value.begin(), value.end(), [](unsigned char c) {
               return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
                      (c >= '0' && c <= '9') || c == '_' || c == '-';
           });
}

InputFrame decode_frame(const Json& json) {
    if (!json.is_object() || !json.contains("version")) {
        throw std::invalid_argument("input frame must be an object with version");
    }
    InputFrame frame;
    frame.version = unsigned_integer(json.at("version"), "version");
    if (frame.version == 1) {
        fields(json, {"version", "source", "seq", "points"});
    } else if (frame.version == 2) {
        fields(json, {"version", "source", "seq", "points", "session_id", "track_id",
                      "captured_s", "detected"});
    } else {
        throw std::invalid_argument("unsupported input protocol version");
    }
    if (!json.at("source").is_string()) throw std::invalid_argument("source must be a string");
    const auto source = json.at("source").get<std::string>();
    if (source == "touch") frame.source = InputSource::Touch;
    else if (source == "camera") frame.source = InputSource::Camera;
    else throw std::invalid_argument("source must be touch or camera");
    frame.seq = unsigned_integer(json.at("seq"), "seq");
    if (frame.version == 2) {
        if (frame.source != InputSource::Camera) {
            throw std::invalid_argument("input protocol v2 requires camera source");
        }
        if (!json.at("session_id").is_string()) {
            throw std::invalid_argument("session_id must be a string");
        }
        frame.session_id = json.at("session_id").get<std::string>();
        if (!valid_session_id(frame.session_id)) {
            throw std::invalid_argument("session_id must contain 1..64 ASCII letters, digits, '_' or '-'");
        }
        frame.track_id = unsigned_integer(json.at("track_id"), "track_id");
        frame.captured_s = finite_number(json.at("captured_s"), "captured_s");
        if (frame.captured_s < 0.0) throw std::invalid_argument("captured_s must be nonnegative");
        if (!json.at("detected").is_boolean()) throw std::invalid_argument("detected must be boolean");
        frame.detected = json.at("detected").get<bool>();
        if (frame.detected && frame.track_id == 0) {
            throw std::invalid_argument("detected camera frame requires a positive track_id");
        }
    }
    const auto& points = json.at("points");
    if (!points.is_object()) throw std::invalid_argument("points must be an object");
    if (frame.version == 2 && !frame.detected && !points.empty()) {
        throw std::invalid_argument("undetected camera frame must have empty points");
    }
    for (auto it = points.begin(); it != points.end(); ++it) {
        if (it.key().empty()) throw std::invalid_argument("landmark name must not be empty");
        const auto& value = it.value();
        fields(value, {"x", "y", "confidence"}, {"valid"});
        Landmark point;
        point.x = unit_number(value.at("x"), "x");
        point.y = unit_number(value.at("y"), "y");
        point.confidence = unit_number(value.at("confidence"), "confidence");
        point.valid = true;
        if (value.contains("valid")) {
            if (!value.at("valid").is_boolean()) throw std::invalid_argument("valid must be boolean");
            point.valid = value.at("valid").get<bool>();
        }
        frame.points.emplace(it.key(), point);
    }
    return frame;
}

bool usable(const Landmark& point, double threshold) {
    return point.valid && std::isfinite(point.x) && std::isfinite(point.y) &&
           std::isfinite(point.confidence) && point.x >= 0.0 && point.x <= 1.0 &&
           point.y >= 0.0 && point.y <= 1.0 && point.confidence >= threshold &&
           point.confidence <= 1.0;
}

const Landmark* get_point(const InputFrame& frame, const char* name, double threshold) {
    const auto found = frame.points.find(name);
    if (found == frame.points.end() || !usable(found->second, threshold)) return nullptr;
    return &found->second;
}

double clamp_unit(double value) { return std::clamp(value, -1.0, 1.0); }

}  // namespace

const char* input_source_name(InputSource source) {
    switch (source) {
        case InputSource::Touch: return "touch";
        case InputSource::Camera: return "camera";
    }
    throw std::invalid_argument("unknown input source enum");
}

InputFrame parse_input_frame(const std::string& json_line) {
    return decode_frame(strict_json(json_line));
}

std::string serialize_input_frame(const InputFrame& frame) {
    if (frame.version == 1 && (!frame.session_id.empty() || frame.track_id != 0 ||
                              frame.captured_s != 0.0 || frame.detected)) {
        throw std::invalid_argument("input protocol v1 cannot carry camera v2 metadata");
    }
    if (!std::isfinite(frame.captured_s)) throw std::invalid_argument("non-finite captured_s");
    Json points = Json::object();
    for (const auto& entry : frame.points) {
        const auto& point = entry.second;
        // JSON would turn NaN into null; reject it before serialization.
        if (!std::isfinite(point.x) || !std::isfinite(point.y) ||
            !std::isfinite(point.confidence)) throw std::invalid_argument("non-finite landmark");
        points[entry.first] = {{"x", point.x}, {"y", point.y},
                               {"confidence", point.confidence}, {"valid", point.valid}};
    }
    Json json = {{"version", frame.version}, {"source", input_source_name(frame.source)},
                 {"seq", frame.seq}, {"points", std::move(points)}};
    if (frame.version == 2) {
        json["session_id"] = frame.session_id;
        json["track_id"] = frame.track_id;
        json["captured_s"] = frame.captured_s;
        json["detected"] = frame.detected;
    }
    decode_frame(json);  // Check programmatically constructed frames as well.
    const auto result = json.dump();
    if (result.size() > kMaxJsonLineBytes) throw std::invalid_argument("serialized input frame too large");
    return result;
}

std::vector<RecordedInput> load_input_replay(const std::string& path) {
    std::ifstream stream(path);
    if (!stream) throw std::runtime_error("cannot open input replay: " + path);
    std::vector<RecordedInput> records;
    std::string line;
    std::size_t line_number = 0;
    while (std::getline(stream, line)) {
        ++line_number;
        if (line.find_first_not_of(" \t\r\n") == std::string::npos) continue;
        try {
            const auto json = strict_json(line);
            fields(json, {"arrival_ms", "frame"});
            const double arrival_ms = finite_number(json.at("arrival_ms"), "arrival_ms");
            if (arrival_ms < 0.0) throw std::invalid_argument("arrival_ms must be nonnegative");
            RecordedInput record{arrival_ms / 1000.0, decode_frame(json.at("frame"))};
            if (!records.empty() && record.arrival_s < records.back().arrival_s) {
                throw std::invalid_argument("arrival_ms must be nondecreasing");
            }
            records.push_back(std::move(record));
        } catch (const std::exception& error) {
            throw std::invalid_argument(path + ":" + std::to_string(line_number) + ": " + error.what());
        }
    }
    if (stream.bad()) throw std::runtime_error("failed while reading input replay: " + path);
    if (records.empty()) throw std::invalid_argument("input replay has no frames: " + path);
    return records;
}

Retargeter::Retargeter(RetargetConfig config) : config_(config) {
    if (!std::isfinite(config_.confidence_threshold) || config_.confidence_threshold < 0.0 ||
        config_.confidence_threshold > 1.0 || !std::isfinite(config_.min_shoulder_width) ||
        config_.min_shoulder_width <= 0.0 || !std::isfinite(config_.hand_span_shoulders) ||
        config_.hand_span_shoulders <= 0.0 || !std::isfinite(config_.neck_gain_x) ||
        !std::isfinite(config_.neck_gain_y) || !std::isfinite(config_.neck_origin_x) ||
        config_.neck_origin_x < 0.0 || config_.neck_origin_x > 1.0 ||
        !std::isfinite(config_.neck_origin_y) || config_.neck_origin_y < 0.0 ||
        config_.neck_origin_y > 1.0) {
        throw std::invalid_argument("invalid retargeting configuration");
    }
}

ShadowPose Retargeter::map(const InputFrame& frame) const {
    ShadowPose pose;
    const double x_sign = config_.mirror_x ? -1.0 : 1.0;
    const auto threshold = config_.confidence_threshold;
    const auto* left = get_point(frame, "left_shoulder", threshold);
    const auto* right = get_point(frame, "right_shoulder", threshold);
    Landmark midpoint;
    const auto* neck = get_point(frame, "neck", threshold);
    if (!neck && left && right) {
        midpoint = {(left->x + right->x) / 2.0, (left->y + right->y) / 2.0,
                    std::min(left->confidence, right->confidence), true};
        neck = &midpoint;
    }
    if (neck) {
        pose.at(RodId::WusongNeck) = {
            clamp_unit(x_sign * config_.neck_gain_x * (neck->x - config_.neck_origin_x)),
            clamp_unit(config_.neck_gain_y * (config_.neck_origin_y - neck->y)), true};
    }
    if (left && right) {
        const double width = std::hypot(right->x - left->x, right->y - left->y);
        const double span = width * config_.hand_span_shoulders;
        if (width >= config_.min_shoulder_width && std::isfinite(span) && span > 0.0) {
            auto hand = [&](const char* name, const Landmark& shoulder, RodId rod) {
                if (const auto* wrist = get_point(frame, name, threshold)) {
                    pose.at(rod) = {
                        clamp_unit(x_sign * (wrist->x - shoulder.x) / span),
                        clamp_unit((shoulder.y - wrist->y) / span), true};
                }
            };
            hand("left_wrist", *left, RodId::WusongLeft);
            hand("right_wrist", *right, RodId::WusongRight);
        }
    }
    // Explicit default for interactive modes; replace with a separate tiger
    // behavior layer later if the team adds idle/attack animation.
    pose.at(RodId::TigerHead) = {0.0, 0.0, true};
    pose.at(RodId::TigerTail) = {0.0, 0.0, true};
    return pose;
}

}  // namespace shadow
