#include "shadow/capture_session.hpp"
#include <nlohmann/json.hpp>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <ctime>
#include <fstream>
#include <iomanip>
#include <limits>
#include <random>
#include <set>
#include <sstream>
#include <stdexcept>
#include <utility>

namespace shadow {
namespace {
using Json = nlohmann::json;

[[noreturn]] void fail(const std::string& message) {
    throw std::runtime_error("capture: " + message);
}
void check(bool ok, const std::string& message) { if (!ok) fail(message); }
bool identifier(const std::string& value) {
    if (value.empty() || value.size() > 128) return false;
    return std::all_of(value.begin(), value.end(), [](unsigned char c) {
        return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
               (c >= '0' && c <= '9') || c == '_' || c == '-' || c == '.';
    }) && value != "." && value != "..";
}
bool text_value(const std::string& value) {
    return !value.empty() && value.size() <= 4096 &&
           std::none_of(value.begin(), value.end(), [](unsigned char c) { return c < 32; });
}
void keys(const Json& j, std::initializer_list<const char*> allowed, const std::string& where) {
    check(j.is_object(), where + " must be an object");
    for (auto it = j.begin(); it != j.end(); ++it) {
        const bool known = std::any_of(allowed.begin(), allowed.end(),
            [&](const char* key) { return it.key() == key; });
        check(known, where + ": unknown field " + it.key());
    }
}
std::string string_field(const Json& j, const char* key) {
    check(j.contains(key) && j.at(key).is_string(), std::string("missing string ") + key);
    const auto value = j.at(key).get<std::string>();
    check(text_value(value), std::string("invalid text ") + key);
    return value;
}
double number_field(const Json& j, const char* key) {
    check(j.contains(key) && j.at(key).is_number(), std::string("missing number ") + key);
    const double value = j.at(key).get<double>();
    check(std::isfinite(value), std::string("nonfinite number ") + key);
    return value;
}
void version_one(const Json& j) {
    check(j.contains("version") && j.at("version").is_number_integer() &&
          j.at("version") == 1, "version must be integer 1");
}
const Json& array_field(const Json& j, const char* key, bool nonempty = true) {
    check(j.contains(key) && j.at(key).is_array(), std::string("missing array ") + key);
    const auto& a = j.at(key);
    check(!nonempty || !a.empty(), std::string("empty array ") + key);
    return a;
}
Json parse_json(const std::string& source) {
    // Reject duplicate object keys; silently retaining the last value is unsafe.
    std::vector<std::set<std::string>> object_keys;
    auto callback = [&](int, Json::parse_event_t event, Json& parsed) {
        if (event == Json::parse_event_t::object_start) object_keys.emplace_back();
        else if (event == Json::parse_event_t::key) {
            check(!object_keys.empty() && object_keys.back().insert(parsed.get<std::string>()).second,
                  "duplicate JSON object key");
        } else if (event == Json::parse_event_t::object_end) object_keys.pop_back();
        return true;
    };
    return Json::parse(source, callback);
}
CaptureSlide read_slide(const Json& j, bool config_controls = false) {
    if (config_controls)
        keys(j, {"id", "unit", "value", "state_kind", "assumption", "controllable",
                 "min", "max", "jog_step", "max_step"}, "slide config");
    else
        keys(j, {"id", "unit", "value", "state_kind", "assumption", "controllable"}, "slide state");
    CaptureSlide s;
    s.id = string_field(j, "id"); s.unit = string_field(j, "unit");
    s.value = number_field(j, "value"); s.state_kind = string_field(j, "state_kind");
    if (j.contains("assumption")) s.assumption = string_field(j, "assumption");
    if (j.contains("controllable")) {
        check(j.at("controllable").is_boolean(), "slide controllable must be boolean");
        s.controllable = j.at("controllable").get<bool>();
    }
    if (config_controls && s.controllable) {
        s.min = number_field(j, "min"); s.max = number_field(j, "max");
        s.jog_step = number_field(j, "jog_step"); s.max_step = number_field(j, "max_step");
    } else if (config_controls) {
        check(!j.contains("min") && !j.contains("max") && !j.contains("jog_step") && !j.contains("max_step"),
              "slide control limits require controllable:true");
    }
    return s;
}
Json slide_json(const CaptureSlide& s) {
    Json j = {{"id", s.id}, {"unit", s.unit}, {"value", s.value}, {"state_kind", s.state_kind},
              {"controllable", s.controllable}};
    if (!s.assumption.empty()) j["assumption"] = s.assumption;
    return j;
}
void valid_slide(const CaptureSlide& s) {
    check(identifier(s.id) && text_value(s.unit) && std::isfinite(s.value), "invalid slide");
    check(s.state_kind == "measured" || s.state_kind == "commanded" ||
          s.state_kind == "fixed_assumption", "invalid slide state_kind");
    check(s.state_kind != "fixed_assumption" || text_value(s.assumption),
          "fixed_assumption slide requires assumption text");
    check(s.assumption.empty() || text_value(s.assumption), "invalid slide assumption");
    if (s.controllable) {
        check(std::isfinite(s.min) && std::isfinite(s.max) && s.min < s.max &&
              s.value >= s.min && s.value <= s.max && std::isfinite(s.jog_step) && s.jog_step > 0 &&
              std::isfinite(s.max_step) && s.max_step > 0 && s.jog_step <= s.max_step,
              "invalid controlled slide limits or steps: " + s.id);
        check(s.state_kind == "commanded" || s.state_kind == "measured",
              "controlled slide cannot be a fixed_assumption: " + s.id);
    }
}
const CaptureSlide& find_slide(const CaptureConfig& config, const std::string& id) {
    const auto found = std::find_if(config.slides.begin(), config.slides.end(),
                                   [&](const CaptureSlide& slide) { return slide.id == id; });
    check(found != config.slides.end(), "unknown slide " + id);
    return *found;
}
int protocol_version(const CaptureConfig& config) {
    return std::any_of(config.slides.begin(), config.slides.end(),
                       [](const CaptureSlide& slide) { return slide.controllable; }) ? 2 : 1;
}
void inherit_slide_control(CaptureSlide& state, const CaptureSlide& config) {
    state.controllable = config.controllable;
    state.min = config.min; state.max = config.max;
    state.jog_step = config.jog_step; state.max_step = config.max_step;
}
bool same_slide_control(const CaptureSlide& state, const CaptureSlide& config) {
    return state.controllable == config.controllable && state.min == config.min &&
           state.max == config.max && state.jog_step == config.jog_step && state.max_step == config.max_step;
}
void validate_step(double from, double to, double maximum, const std::string& id) {
    const double rounding = std::numeric_limits<double>::epsilon() * 8 *
                            std::max({1.0, std::abs(from), std::abs(to), maximum});
    check(std::abs(to - from) <= maximum + rounding, "step exceeds max_step: " + id);
}
const CaptureAxis& find_axis(const CaptureConfig& config, const std::string& id) {
    const auto found = std::find_if(config.axes.begin(), config.axes.end(),
                                   [&](const CaptureAxis& a) { return a.id == id; });
    check(found != config.axes.end(), "unknown axis " + id);
    return *found;
}
std::map<std::string, double> values_map(const CaptureConfig& config,
                                       const std::vector<CaptureAxisValue>& values, bool full) {
    std::map<std::string, double> result;
    for (const auto& v : values) {
        const auto& a = find_axis(config, v.axis_id);
        check(v.unit == a.unit, "unit mismatch for axis " + a.id);
        check(std::isfinite(v.value) && v.value >= a.min && v.value <= a.max,
              "axis outside limits: " + a.id);
        check(result.emplace(v.axis_id, v.value).second, "duplicate axis " + v.axis_id);
    }
    check(!values.empty(), "axis state must not be empty");
    check(!full || result.size() == config.axes.size(), "state must include every axis");
    return result;
}
void validate_map(const CaptureConfig& config, const std::map<std::string, double>& values) {
    check(values.size() == config.axes.size(), "target must include every axis");
    for (const auto& item : values) {
        const auto& a = find_axis(config, item.first);
        check(std::isfinite(item.second) && item.second >= a.min && item.second <= a.max,
              "target outside limits: " + a.id);
    }
}
std::vector<CaptureAxisValue> axis_values(const CaptureConfig& config,
                                         const std::map<std::string, double>& values) {
    std::vector<CaptureAxisValue> result;
    for (const auto& a : config.axes) result.push_back({a.id, values.at(a.id), a.unit});
    return result;
}
Json axes_json(const std::vector<CaptureAxisValue>& axes) {
    auto j = Json::array();
    for (const auto& a : axes) j.push_back({{"axis_id", a.axis_id}, {"value", a.value}, {"unit", a.unit}});
    return j;
}
Json slides_json(const std::vector<CaptureSlide>& slides) {
    auto j = Json::array();
    for (const auto& s : slides) j.push_back(slide_json(s));
    return j;
}
Json state_json(const CaptureState& state) {
    Json j = {{"axes", axes_json(state.axes)}, {"slides", slides_json(state.slides)},
              {"backend", state.backend}, {"accepted", state.accepted}, {"confirmed", state.confirmed}};
    j["feedback"] = state.feedback ? axes_json(*state.feedback) : Json(nullptr);
    return j;
}
std::vector<CaptureAxisValue> read_axes(const Json& list) {
    std::vector<CaptureAxisValue> result;
    for (const auto& j : list) {
        keys(j, {"axis_id", "value", "unit"}, "axis value");
        result.push_back({string_field(j, "axis_id"), number_field(j, "value"), string_field(j, "unit")});
    }
    return result;
}
void valid_state(const CaptureConfig& config, const CaptureState& state) {
    values_map(config, state.axes, true);
    if (state.feedback) values_map(config, *state.feedback, false);
    check(state.slides.size() == config.slides.size(), "state must include every slide");
    std::set<std::string> ids;
    for (const auto& slide : state.slides) {
        valid_slide(slide);
        check(ids.insert(slide.id).second, "duplicate slide " + slide.id);
        const auto& configured = find_slide(config, slide.id);
        check(slide.unit == configured.unit, "slide unit mismatch " + slide.id);
        check(same_slide_control(slide, configured), "slide control config mismatch " + slide.id);
    }
    check(state.backend == "simulation" || state.backend == "external" ||
          state.backend == "manual_unconfirmed", "invalid backend");
    check(state.accepted, "state was not accepted");
    check(state.backend == "manual_unconfirmed" ? !state.confirmed : state.confirmed,
          "backend confirmation flags disagree");
}
Json config_json(const CaptureConfig& c) {
    auto axes = Json::array();
    for (const auto& a : c.axes) axes.push_back({{"id", a.id}, {"rod", a.rod}, {"unit", a.unit},
        {"min", a.min}, {"max", a.max}, {"initial", a.initial},
        {"jog_step", a.jog_step}, {"max_step", a.max_step}});
    auto points = Json::array();
    for (const auto& p : c.points) points.push_back({{"id", p.id}, {"rod", p.rod}, {"axes", p.axes}});
    auto slides = slides_json(c.slides);
    for (std::size_t i = 0; i < c.slides.size(); ++i) {
        const auto& s = c.slides[i];
        if (s.controllable) {
            slides[i]["min"] = s.min; slides[i]["max"] = s.max;
            slides[i]["jog_step"] = s.jog_step; slides[i]["max_step"] = s.max_step;
        }
    }
    return {{"version", c.version}, {"simulation_only", c.simulation_only},
        {"stage", {{"width_mm", c.stage_width_mm}, {"height_mm", c.stage_height_mm}}},
        {"reference_view", c.reference_view}, {"reference_points_mm", c.reference_points_mm},
        {"axes", axes}, {"slides", slides}, {"points", points}};
}
void write_file(const std::filesystem::path& path, const std::uint8_t* data,
                std::size_t size, bool exclusive) {
    std::FILE* stream = nullptr;
#ifdef _WIN32
    stream = _wfopen(path.c_str(), exclusive ? L"wbx" : L"ab");
#else
    stream = std::fopen(path.c_str(), exclusive ? "wbx" : "ab");
#endif
    check(stream != nullptr, "cannot open file " + path.string());
    const bool written = std::fwrite(data, 1, size, stream) == size;
    const bool flushed = std::fflush(stream) == 0;
    const bool closed = std::fclose(stream) == 0;
    if (exclusive && !(written && flushed && closed)) {
        std::error_code ignored;
        std::filesystem::remove(path, ignored);
    }
    check(written && flushed && closed, "cannot write file " + path.string());
}
void write_text(const std::filesystem::path& path, const std::string& text, bool exclusive) {
    write_file(path, reinterpret_cast<const std::uint8_t*>(text.data()), text.size(), exclusive);
}
std::uint32_t be32(const std::vector<std::uint8_t>& bytes, std::size_t at) {
    return (static_cast<std::uint32_t>(bytes.at(at)) << 24) |
           (static_cast<std::uint32_t>(bytes.at(at + 1)) << 16) |
           (static_cast<std::uint32_t>(bytes.at(at + 2)) << 8) | bytes.at(at + 3);
}
std::uint32_t crc32(const std::vector<std::uint8_t>& bytes, std::size_t at, std::size_t size) {
    std::uint32_t crc = 0xffffffffU;
    for (std::size_t i = at; i < at + size; ++i) {
        crc ^= bytes[i];
        for (int bit = 0; bit < 8; ++bit) crc = (crc >> 1) ^ ((crc & 1U) ? 0xedb88320U : 0U);
    }
    return crc ^ 0xffffffffU;
}
void validate_png(const std::vector<std::uint8_t>& bytes, int width, int height) {
    const std::array<std::uint8_t, 8> signature{137, 80, 78, 71, 13, 10, 26, 10};
    check(bytes.size() >= 45 && std::equal(signature.begin(), signature.end(), bytes.begin()),
          "frame is not a PNG");
    bool header = false, data = false, ended = false;
    for (std::size_t pos = 8; pos < bytes.size();) {
        check(bytes.size() - pos >= 12, "truncated PNG chunk");
        const auto length = static_cast<std::size_t>(be32(bytes, pos));
        check(length <= bytes.size() - pos - 12, "truncated PNG data");
        const std::string kind(reinterpret_cast<const char*>(&bytes[pos + 4]), 4);
        check(be32(bytes, pos + 8 + length) == crc32(bytes, pos + 4, length + 4), "bad PNG CRC");
        if (!header) {
            check(kind == "IHDR" && length == 13, "PNG must start with IHDR");
            check(be32(bytes, pos + 8) == static_cast<std::uint32_t>(width) &&
                  be32(bytes, pos + 12) == static_cast<std::uint32_t>(height),
                  "PNG dimensions differ from frozen frame");
            header = true;
        } else check(kind != "IHDR", "duplicate PNG header");
        if (kind == "IDAT") data = data || length > 0;
        pos += length + 12;
        if (kind == "IEND") {
            check(length == 0 && pos == bytes.size(), "invalid PNG end"); ended = true; break;
        }
    }
    check(header && data && ended, "incomplete PNG frame");
}
std::string new_session_id() {
    std::random_device random;
    std::ostringstream out;
    out << "capture-" << std::chrono::system_clock::now().time_since_epoch().count() << '-'
        << std::hex << random() << random();
    return out.str();
}
std::string decimal(double value) {
    std::ostringstream out; out.imbue(std::locale::classic());
    out << std::setprecision(std::numeric_limits<double>::max_digits10) << value;
    return out.str();
}
} // namespace

bool valid_capture_rod(const std::string& rod) {
    return rod == "wusong_neck" || rod == "wusong_left" || rod == "wusong_right" ||
           rod == "tiger_head" || rod == "tiger_tail" || rod == "tiger_leg";
}

CaptureConfig parse_capture_config(const std::string& source, const std::string& source_path) {
    const auto j = parse_json(source);
    keys(j, {"version", "simulation_only", "stage", "reference_view", "reference_points_mm",
             "axes", "slides", "points"}, "config");
    version_one(j);
    CaptureConfig c; c.source_path = source_path; c.source_json = source;
    if (j.contains("simulation_only")) {
        check(j.at("simulation_only").is_boolean(), "simulation_only must be boolean");
        c.simulation_only = j.at("simulation_only").get<bool>();
    }
    check(j.contains("stage"), "missing stage");
    keys(j.at("stage"), {"width_mm", "height_mm"}, "stage");
    c.stage_width_mm = number_field(j.at("stage"), "width_mm");
    c.stage_height_mm = number_field(j.at("stage"), "height_mm");
    c.reference_view = string_field(j, "reference_view");
    c.reference_points_mm = {{{0, 0}, {c.stage_width_mm, 0},
                             {c.stage_width_mm, c.stage_height_mm}, {0, c.stage_height_mm}}};
    if (j.contains("reference_points_mm")) {
        const auto& points = array_field(j, "reference_points_mm");
        check(points.size() == 4, "reference_points_mm requires four points");
        for (std::size_t i = 0; i < 4; ++i) {
            check(points[i].is_array() && points[i].size() == 2 &&
                  points[i][0].is_number() && points[i][1].is_number(), "invalid reference point");
            c.reference_points_mm[i] = {points[i][0].get<double>(), points[i][1].get<double>()};
        }
    }
    for (const auto& item : array_field(j, "axes")) {
        keys(item, {"id", "rod", "unit", "min", "max", "initial", "jog_step", "max_step"}, "axis");
        c.axes.push_back({string_field(item, "id"), string_field(item, "rod"),
            string_field(item, "unit"), number_field(item, "min"), number_field(item, "max"),
            number_field(item, "initial"), number_field(item, "jog_step"), number_field(item, "max_step")});
    }
    for (const auto& item : array_field(j, "slides")) c.slides.push_back(read_slide(item, true));
    const auto point_list = j.contains("points") ? array_field(j, "points", false) : Json::array();
    for (const auto& item : point_list) {
        keys(item, {"id", "rod", "axes"}, "point");
        CapturePoint point; point.id = string_field(item, "id"); point.rod = string_field(item, "rod");
        check(item.contains("axes") && item.at("axes").is_object(), "point axes must be an object");
        for (auto it = item.at("axes").begin(); it != item.at("axes").end(); ++it) {
            check(it.value().is_number(), "point axis must be numeric");
            point.axes.emplace(it.key(), it.value().get<double>());
        }
        c.points.push_back(std::move(point));
    }
    validate_capture_config(c);
    return c;
}
CaptureConfig load_capture_config(const std::filesystem::path& path) {
    std::ifstream input(path, std::ios::binary);
    check(static_cast<bool>(input), "cannot read config " + path.string());
    std::ostringstream buffer; buffer << input.rdbuf();
    check(!input.bad(), "cannot read complete config");
    return parse_capture_config(buffer.str(), std::filesystem::absolute(path).string());
}
void validate_capture_config(const CaptureConfig& c) {
    check(c.version == 1, "unsupported config version");
    check(std::isfinite(c.stage_width_mm) && c.stage_width_mm > 0 &&
          std::isfinite(c.stage_height_mm) && c.stage_height_mm > 0, "invalid stage dimensions");
    check(c.reference_view == "rear" || c.reference_view == "front", "reference_view must be rear or front");
    double direction = 0;
    for (std::size_t i = 0; i < 4; ++i) {
        const auto& a = c.reference_points_mm[i];
        const auto& b = c.reference_points_mm[(i + 1) % 4];
        const auto& d = c.reference_points_mm[(i + 2) % 4];
        check(std::isfinite(a[0]) && std::isfinite(a[1]) && a[0] >= 0 && a[0] <= c.stage_width_mm &&
              a[1] >= 0 && a[1] <= c.stage_height_mm, "reference point outside stage");
        const double cross = (b[0] - a[0]) * (d[1] - b[1]) - (b[1] - a[1]) * (d[0] - b[0]);
        check(std::isfinite(cross) && std::abs(cross) > 1e-12, "degenerate reference points");
        if (i == 0) direction = cross;
        else check((cross > 0) == (direction > 0), "reference points must form a convex quadrilateral");
    }
    check(!c.axes.empty() && !c.slides.empty(), "axes and slides must not be empty");
    std::set<std::string> ids;
    for (const auto& a : c.axes) {
        check(identifier(a.id) && ids.insert(a.id).second, "invalid or duplicate axis id");
        check(valid_capture_rod(a.rod) && text_value(a.unit), "invalid axis rod or unit");
        check(std::isfinite(a.min) && std::isfinite(a.max) && a.min < a.max &&
              std::isfinite(a.initial) && a.initial >= a.min && a.initial <= a.max &&
              std::isfinite(a.jog_step) && a.jog_step > 0 &&
              std::isfinite(a.max_step) && a.max_step > 0 && a.jog_step <= a.max_step,
              "invalid axis limits or steps: " + a.id);
    }
    ids.clear();
    for (const auto& s : c.slides) { valid_slide(s); check(ids.insert(s.id).second, "duplicate slide id"); }
    ids.clear();
    for (const auto& p : c.points) {
        check(identifier(p.id) && ids.insert(p.id).second, "invalid or duplicate point id");
        check(valid_capture_rod(p.rod), "invalid point rod");
        check(std::any_of(c.axes.begin(), c.axes.end(), [&](const CaptureAxis& a) { return a.rod == p.rod; }),
              "point rod has no configured axes");
        validate_map(c, p.axes);
    }
}
void validate_capture_transition(const CaptureConfig& c, const std::map<std::string, double>& from,
                                 const std::map<std::string, double>& to) {
    validate_map(c, from); validate_map(c, to);
    for (const auto& a : c.axes) {
        validate_step(from.at(a.id), to.at(a.id), a.max_step, a.id);
    }
}
std::string capture_utc_now() {
    const auto now = std::chrono::system_clock::now();
    const auto time = std::chrono::system_clock::to_time_t(now);
    std::tm utc{};
#ifdef _WIN32
    gmtime_s(&utc, &time);
#else
    gmtime_r(&time, &utc);
#endif
    std::ostringstream out; out << std::put_time(&utc, "%Y-%m-%dT%H:%M:%SZ");
    return out.str();
}
std::string capture_csv_escape(const std::string& value) {
    if (value.find_first_of(",\"\r\n") == std::string::npos) return value;
    std::string result = "\"";
    for (char c : value) { if (c == '"') result += '"'; result += c; }
    return result + '"';
}
CaptureState parse_capture_ack(const CaptureConfig& config, const CaptureRequest& request,
                               const std::string& source) {
    const auto j = parse_json(source);
    keys(j, {"version", "type", "session_id", "seq", "accepted", "adopted", "feedback", "slides", "fault"}, "ACK");
    const int expected_version = protocol_version(config);
    check(j.contains("version") && j.at("version").is_number_integer() &&
          j.at("version") == expected_version, "ACK version does not match configured slide control protocol");
    check(string_field(j, "type") == "capture_ack", "wrong ACK type");
    check(string_field(j, "session_id") == request.session_id, "ACK session mismatch");
    check(j.contains("seq") && j.at("seq").is_number_unsigned() &&
          j.at("seq").get<std::uint64_t>() == request.seq && request.seq > 0, "ACK sequence mismatch");
    check(j.contains("accepted") && j.at("accepted").is_boolean() && j.at("accepted").get<bool>(),
          "target was rejected by adapter");
    if (j.contains("fault")) {
        const auto& fault = j.at("fault");
        const bool clear = fault.is_null() || (fault.is_boolean() && !fault.get<bool>()) ||
                           (fault.is_string() && fault.get<std::string>().empty()) ||
                           ((fault.is_array() || fault.is_object()) && fault.empty());
        check(clear, "adapter reported a fault");
    }
    CaptureState state; state.backend = "external"; state.accepted = state.confirmed = true;
    state.axes = read_axes(array_field(j, "adopted"));
    if (j.contains("feedback") && !j.at("feedback").is_null())
        state.feedback = read_axes(array_field(j, "feedback"));
    for (const auto& j_slide : array_field(j, "slides")) {
        auto slide = read_slide(j_slide);
        const auto& configured = find_slide(config, slide.id);
        check(!j_slide.contains("controllable") || slide.controllable == configured.controllable,
              "ACK slide controllable mismatch " + slide.id);
        inherit_slide_control(slide, configured);
        state.slides.push_back(std::move(slide));
    }
    valid_state(config, state);
    std::vector<CaptureSlide> ordered;
    for (const auto& configured : config.slides) {
        const auto found = std::find_if(state.slides.begin(), state.slides.end(),
                                       [&](const CaptureSlide& slide) { return slide.id == configured.id; });
        ordered.push_back(*found);
    }
    state.slides = std::move(ordered);
    return state;
}

CaptureSession::CaptureSession(const std::filesystem::path& directory, CaptureConfig config,
                               std::string backend)
    : directory_(std::filesystem::absolute(directory).lexically_normal()), config_(std::move(config)),
      backend_(std::move(backend)), session_id_(new_session_id()) {
    validate_capture_config(config_);
    check(backend_ == "simulation" || backend_ == "external" || backend_ == "manual_unconfirmed", "invalid backend");
    check(!(backend_ == "external" && config_.simulation_only), "simulation_only config cannot use external backend");
    check(!std::filesystem::exists(directory_), "session directory already exists");
    std::filesystem::create_directories(directory_.parent_path());
    check(std::filesystem::create_directory(directory_), "cannot create new session directory");
    std::filesystem::create_directory(directory_ / "frames");
    std::filesystem::create_directory(directory_ / "outbox");
    std::filesystem::create_directory(directory_ / "inbox");
    state_.backend = backend_; state_.slides = config_.slides;
    state_.accepted = backend_ != "external";
    state_.confirmed = backend_ == "simulation";
    synchronized_ = backend_ != "external";
    for (const auto& a : config_.axes) state_.axes.push_back({a.id, a.initial, a.unit});
    const Json metadata = {{"version", 1}, {"type", "capture_session"}, {"session_id", session_id_},
        {"created_at", capture_utc_now()}, {"backend", backend_}, {"source_config", config_.source_path},
        {"request_protocol_version", protocol_version(config_)},
        {"config_snapshot", "config.snapshot.json"}, {"authoritative_samples", "samples.jsonl"},
        {"reference_view", config_.reference_view}, {"simulation_only", config_.simulation_only}};
    write_text(directory_ / "metadata.json", metadata.dump(2) + '\n', true);
    write_text(directory_ / "config.snapshot.json", config_.source_json.empty() ?
               config_json(config_).dump(2) + '\n' : config_.source_json, true);
    write_text(directory_ / "requests.jsonl", "", true);
    write_text(directory_ / "samples.jsonl", "", true);
    write_text(directory_ / "samples.csv",
        "session_id,sample_id,seq,rod,pixel_x,pixel_y,stage_x_mm,stage_y_mm,frame_path,axes_json,slides_json,feedback_json,backend,calibration_id,accepted,confirmed,frozen_at,image_width,image_height,frame_read_at\n", true);
}
std::map<std::string, double> CaptureSession::adopted_axes() const {
    return values_map(config_, state_.axes, true);
}
std::map<std::string, double> CaptureSession::adopted_slides() const {
    std::map<std::string, double> result;
    for (const auto& slide : state_.slides) result.emplace(slide.id, slide.value);
    return result;
}
CaptureRequest CaptureSession::make_request(const std::map<std::string, double>& target,
                                            const std::string& type,
                                            const std::map<std::string, double>& slide_targets) {
    check(type == "capture_target" || type == "capture_sync", "invalid request type");
    check(!pending_, "an external request is still pending");
    check(type != "capture_sync" || backend_ == "external", "sync is only valid for external backend");
    check(type != "capture_sync" || slide_targets.empty(), "sync cannot carry new slide targets");
    check(type != "capture_target" || synchronized_, "external backend requires synchronization");
    validate_map(config_, target);
    // Manual entries record commands already used by another tool, without motion.
    if (type == "capture_target" && backend_ != "manual_unconfirmed")
        validate_capture_transition(config_, adopted_axes(), target);
    auto target_slides = state_.slides;
    for (const auto& item : slide_targets) {
        const auto& configured = find_slide(config_, item.first);
        check(configured.controllable, "slide is recorded state only: " + item.first);
        check(std::isfinite(item.second) && item.second >= configured.min && item.second <= configured.max,
              "slide target outside limits: " + item.first);
        auto found = std::find_if(target_slides.begin(), target_slides.end(),
                                 [&](const CaptureSlide& slide) { return slide.id == item.first; });
        check(found != target_slides.end(), "slide has no adopted state: " + item.first);
        if (backend_ != "manual_unconfirmed") validate_step(found->value, item.second, configured.max_step, item.first);
        found->value = item.second;
    }
    if (type == "capture_target") {
        for (auto& slide : target_slides) if (slide.controllable) {
            slide.state_kind = "commanded"; slide.assumption.clear();
        }
    }
    check(next_seq_ != 0, "request sequence exhausted");
    CaptureRequest request; request.session_id = session_id_; request.seq = next_seq_;
    request.type = type; request.axes = axis_values(config_, target);
    request.version = protocol_version(config_); request.slides = std::move(target_slides);
    Json request_json = {{"version", request.version}, {"type", type}, {"session_id", session_id_},
                         {"seq", request.seq}, {"axes", axes_json(request.axes)}};
    if (request.version == 2) request_json["slides"] = slides_json(request.slides);
    request.json = request_json.dump();
    write_text(directory_ / "requests.jsonl", request.json + '\n', false);
    ++next_seq_;
    if (backend_ == "external") pending_ = request;
    else {
        state_.axes = request.axes; state_.slides = request.slides;
        state_.feedback.reset(); state_.accepted = true;
        state_.confirmed = backend_ == "simulation"; adopted_seq_ = request.seq;
    }
    return request;
}
CaptureState CaptureSession::accept_ack(const CaptureRequest& request, const std::string& source) {
    check(backend_ == "external", "ACK is only valid for external backend");
    try {
        check(pending_ && request.seq == pending_->seq && request.session_id == session_id_ &&
              request.json == pending_->json, "ACK has no matching pending request");
        auto state = parse_capture_ack(config_, *pending_, source);
        state_ = std::move(state); adopted_seq_ = request.seq;
        pending_.reset(); synchronized_ = true;
        return state_;
    } catch (...) { invalidate_external(); throw; }
}
void CaptureSession::invalidate_external() {
    if (backend_ != "external") return;
    synchronized_ = false; pending_.reset(); state_.accepted = state_.confirmed = false;
}
void CaptureSession::update_manual_slides(const std::vector<CaptureSlide>& slides) {
    check(backend_ == "manual_unconfirmed" && !pending_, "manual slide update is only valid in manual mode");
    CaptureState candidate = state_; candidate.slides = slides;
    valid_state(config_, candidate);
    for (const auto& slide : slides) {
        if (slide.controllable) {
            const auto found = std::find_if(state_.slides.begin(), state_.slides.end(),
                                           [&](const CaptureSlide& current) { return current.id == slide.id; });
            check(found != state_.slides.end() && slide_json(slide) == slide_json(*found),
                  "controlled manual slides must be submitted through make_request");
        } else {
            check(slide.state_kind == "fixed_assumption" && text_value(slide.assumption),
                  "manually entered slides must declare a fixed_assumption");
        }
    }
    state_ = std::move(candidate);
}
void CaptureSession::record_sample(const CaptureSample& sample, const std::vector<std::uint8_t>& png) {
    check(identifier(sample.sample_id), "invalid sample id");
    check(std::find(sample_ids_.begin(), sample_ids_.end(), sample.sample_id) == sample_ids_.end(), "duplicate sample id");
    check(valid_capture_rod(sample.rod) && std::any_of(config_.axes.begin(), config_.axes.end(),
          [&](const CaptureAxis& a) { return a.rod == sample.rod; }), "invalid sample rod");
    check(!pending_ && synchronized_ && sample.seq == adopted_seq_ && adopted_seq_ != 0,
          "sample does not match an accepted current request");
    valid_state(config_, sample.state);
    check(state_json(sample.state) == state_json(state_), "sample state is stale or altered");
    check(sample.image_width > 0 && sample.image_height > 0 && std::isfinite(sample.pixel_x) &&
          std::isfinite(sample.pixel_y) && sample.pixel_x >= 0 && sample.pixel_y >= 0 &&
          sample.pixel_x < sample.image_width && sample.pixel_y < sample.image_height,
          "invalid frozen frame or pixel coordinate");
    check(std::isfinite(sample.stage_x_mm) && std::isfinite(sample.stage_y_mm) &&
          sample.stage_x_mm >= 0 && sample.stage_x_mm <= config_.stage_width_mm &&
          sample.stage_y_mm >= 0 && sample.stage_y_mm <= config_.stage_height_mm,
          "stage coordinate outside limits");
    check(text_value(sample.frozen_at) && text_value(sample.calibration_id), "missing freeze time or calibration id");
    check(!sample.frame_read_at || text_value(*sample.frame_read_at), "invalid frame read timestamp");
    const auto frame_relative = std::filesystem::path(sample.frame_path);
    check(!frame_relative.empty() && !frame_relative.is_absolute() && !frame_relative.has_root_name() &&
          frame_relative.parent_path() == std::filesystem::path("frames") &&
          frame_relative.extension() == ".png" && identifier(frame_relative.stem().string()),
          "frame_path must be frames/<safe name>.png");
    const auto frame = directory_ / frame_relative;
    check(!std::filesystem::exists(frame), "frame path already exists");
    validate_png(png, sample.image_width, sample.image_height);
    Json json = {{"version", 1}, {"type", "capture_sample"}, {"session_id", session_id_},
        {"sample_id", sample.sample_id}, {"seq", sample.seq}, {"rod", sample.rod},
        {"pixel", {{"x", sample.pixel_x}, {"y", sample.pixel_y}, {"width", sample.image_width}, {"height", sample.image_height}}},
        {"stage_mm", {{"x", sample.stage_x_mm}, {"y", sample.stage_y_mm}}},
        {"frame_path", sample.frame_path}, {"frozen_at", sample.frozen_at},
        {"calibration_id", sample.calibration_id}, {"state", state_json(sample.state)},
        {"reference_view", config_.reference_view}};
    json["frame_read_at"] = sample.frame_read_at ? Json(*sample.frame_read_at) : Json(nullptr);
    const auto& state = sample.state;
    std::vector<std::string> columns{session_id_, sample.sample_id, std::to_string(sample.seq), sample.rod,
        decimal(sample.pixel_x), decimal(sample.pixel_y), decimal(sample.stage_x_mm), decimal(sample.stage_y_mm),
        sample.frame_path, axes_json(state.axes).dump(), slides_json(state.slides).dump(),
        state.feedback ? axes_json(*state.feedback).dump() : "null", state.backend, sample.calibration_id,
        state.accepted ? "true" : "false", state.confirmed ? "true" : "false", sample.frozen_at,
        std::to_string(sample.image_width), std::to_string(sample.image_height),
        sample.frame_read_at ? *sample.frame_read_at : ""};
    std::string row;
    for (std::size_t i = 0; i < columns.size(); ++i) {
        if (i) row += ',';
        row += capture_csv_escape(columns[i]);
    }
    row += '\n';
    const auto json_path = directory_ / "samples.jsonl", csv_path = directory_ / "samples.csv";
    const auto json_size = std::filesystem::file_size(json_path), csv_size = std::filesystem::file_size(csv_path);
    write_file(frame, png.data(), png.size(), true);
    try {
        write_text(json_path, json.dump() + '\n', false);
        write_text(csv_path, row, false);
    } catch (...) {
        std::error_code ignored;
        std::filesystem::resize_file(json_path, json_size, ignored);
        std::filesystem::resize_file(csv_path, csv_size, ignored);
        std::filesystem::remove(frame, ignored);
        throw;
    }
    sample_ids_.push_back(sample.sample_id);
}
} // namespace shadow
