#include <algorithm>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <locale>
#include <map>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
struct Sample {
    double time = 0.0;
    double angle = 0.0;
    double target = 0.0;
    std::string state;
    std::string mode;
    bool input_clamped = false;
    bool angle_limited = false;
    bool speed_limited = false;
};
struct Axis {
    std::string id;
    std::string rod;
    std::vector<Sample> samples;
};

[[noreturn]] void fail(std::size_t line, const std::string& message) {
    throw std::runtime_error("CSV line " + std::to_string(line) + ": " + message);
}

std::string trim(const std::string& value) {
    const auto first = value.find_first_not_of(" \t\r\n");
    if (first == std::string::npos) return {};
    return value.substr(first, value.find_last_not_of(" \t\r\n") - first + 1);
}

// Quoted CSV fields and doubled quotes are accepted. A record occupies one line.
std::vector<std::string> split_csv(const std::string& record, std::size_t line) {
    std::vector<std::string> fields;
    std::size_t position = 0;
    while (true) {
        std::string value;
        while (position < record.size() && (record[position] == ' ' || record[position] == '\t')) ++position;
        if (position < record.size() && record[position] == '"') {
            ++position;
            bool closed = false;
            while (position < record.size()) {
                const char c = record[position++];
                if (c != '"') value += c;
                else if (position < record.size() && record[position] == '"') {
                    value += '"';
                    ++position;
                } else {
                    closed = true;
                    break;
                }
            }
            if (!closed) fail(line, "unterminated quoted field (multiline fields are unsupported)");
            while (position < record.size() && (record[position] == ' ' || record[position] == '\t' || record[position] == '\r')) ++position;
            if (position < record.size() && record[position] != ',') fail(line, "unexpected text after closing quote");
        } else {
            while (position < record.size() && record[position] != ',') {
                if (record[position] == '"') fail(line, "quote must begin a CSV field");
                value += record[position++];
            }
        }
        fields.push_back(trim(value));
        if (position == record.size()) break;
        ++position;
    }
    return fields;
}

double number(const std::string& value, const std::string& name, std::size_t line) {
    std::istringstream stream(value);
    stream.imbue(std::locale::classic());
    double result = 0.0;
    if (!(stream >> result) || !std::isfinite(result)) fail(line, name + " must be a finite number");
    stream >> std::ws;
    if (!stream.eof()) fail(line, name + " contains trailing text");
    return result;
}

bool boolean(const std::string& value, const std::string& name, std::size_t line) {
    if (value == "0" || value == "false") return false;
    if (value == "1" || value == "true") return true;
    fail(line, name + " must be 0 or 1 (or false/true)");
}

void label(const std::string& value, const std::string& name, std::size_t line) {
    if (value.empty()) fail(line, name + " cannot be empty");
    for (const unsigned char c : value) {
        if (c < 0x20 || c == 0x7f) fail(line, name + " contains a control character");
    }
}

std::string xml(const std::string& value) {
    std::string escaped;
    for (const char c : value) {
        switch (c) {
            case '&': escaped += "&amp;"; break;
            case '<': escaped += "&lt;"; break;
            case '>': escaped += "&gt;"; break;
            case '"': escaped += "&quot;"; break;
            case '\'': escaped += "&apos;"; break;
            default: escaped += c;
        }
    }
    return escaped;
}

std::vector<Axis> read_trace(const std::string& path) {
    std::ifstream input(path);
    if (!input) throw std::runtime_error("Cannot open input: " + path);
    std::string record;
    std::size_t line = 0;
    std::map<std::string, std::size_t> columns;
    std::map<std::string, std::size_t> axis_indices;
    std::vector<Axis> axes;
    while (std::getline(input, record)) {
        ++line;
        if (line == 1 && record.compare(0, 3, "\xef\xbb\xbf") == 0) record.erase(0, 3);
        if (trim(record).empty()) continue;
        const auto fields = split_csv(record, line);
        if (columns.empty()) {
            for (std::size_t i = 0; i < fields.size(); ++i) {
                label(fields[i], "column name", line);
                if (!columns.emplace(fields[i], i).second) fail(line, "duplicate column: " + fields[i]);
            }
            for (const auto* required : {"time_s", "axis_id", "rod", "angle_deg", "limited_target_deg", "input_state", "input_clamped", "angle_limited", "speed_limited"}) {
                if (!columns.count(required)) fail(line, std::string("missing column: ") + required);
            }
            continue;
        }
        if (fields.size() != columns.size()) fail(line, "expected " + std::to_string(columns.size()) + " fields, got " + std::to_string(fields.size()));
        const auto field = [&](const std::string& name) -> const std::string& { return fields.at(columns.at(name)); };
        Sample sample;
        sample.time = number(field("time_s"), "time_s", line);
        sample.angle = number(field("angle_deg"), "angle_deg", line);
        sample.target = number(field("limited_target_deg"), "limited_target_deg", line);
        if (sample.time < 0.0) fail(line, "time_s cannot be negative");
        sample.state = field("input_state");
        label(sample.state, "input_state", line);
        sample.input_clamped = boolean(field("input_clamped"), "input_clamped", line);
        sample.angle_limited = boolean(field("angle_limited"), "angle_limited", line);
        sample.speed_limited = boolean(field("speed_limited"), "speed_limited", line);
        if (columns.count("mode")) {
            sample.mode = field("mode");
            label(sample.mode, "mode", line);
        }
        if (columns.count("playback_s") && number(field("playback_s"), "playback_s", line) < 0.0) fail(line, "playback_s cannot be negative");
        const auto& id = field("axis_id");
        const auto& rod = field("rod");
        label(id, "axis_id", line);
        label(rod, "rod", line);
        const auto insertion = axis_indices.emplace(id, axes.size());
        if (insertion.second) axes.push_back({id, rod, {}});
        auto& axis = axes.at(insertion.first->second);
        if (axis.rod != rod) fail(line, "rod changed for axis " + id);
        if (!axis.samples.empty() && sample.time <= axis.samples.back().time) fail(line, "time_s must strictly increase within axis " + id);
        axis.samples.push_back(sample);
    }
    if (input.bad()) throw std::runtime_error("Failed while reading input: " + path);
    if (axes.empty()) throw std::runtime_error("CSV contains no axis samples");
    return axes;
}

std::string value_text(double value) {
    std::ostringstream text;
    text.imbue(std::locale::classic());
    text << std::setprecision(6) << value;
    return text.str();
}

double median_interval(const Axis& axis) {
    if (axis.samples.size() < 2) return 0.0;
    std::vector<double> intervals;
    for (std::size_t i = 1; i < axis.samples.size(); ++i) intervals.push_back(axis.samples[i].time - axis.samples[i - 1].time);
    const auto mid = intervals.begin() + static_cast<std::ptrdiff_t>(intervals.size() / 2);
    std::nth_element(intervals.begin(), mid, intervals.end());
    return *mid;
}

void write_svg(const std::string& path, const std::vector<Axis>& axes) {
    constexpr double width = 1400.0, left = 95.0, plot_width = 1265.0;
    constexpr double panel_height = 280.0, header_height = 180.0, plot_height = 155.0;
    const double height = header_height + panel_height * static_cast<double>(axes.size()) + 30.0;
    double start = axes.front().samples.front().time, end = start;
    std::size_t count = 0;
    for (const auto& axis : axes) {
        start = std::min(start, axis.samples.front().time);
        end = std::max(end, axis.samples.back().time);
        count += axis.samples.size();
    }
    // Nonnegative times make this subtraction safe for all finite inputs.
    const double span = end > start ? end - start : 1.0;
    const auto x = [&](double time) { return left + (time - start) / span * plot_width; };
    // Refusing existing output also protects a CSV passed under an alias or hard link.
    // This is a local CLI safeguard, not an atomic filesystem locking protocol.
    std::ifstream existing(path, std::ios::binary);
    if (existing) throw std::runtime_error("Output already exists; choose a new SVG filename: " + path);
    std::ofstream output(path, std::ios::trunc);
    if (!output) throw std::runtime_error("Cannot open SVG output: " + path);
    output.imbue(std::locale::classic());
    output << std::fixed << std::setprecision(3)
           << "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
           << "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"" << width << "\" height=\"" << height
           << "\" viewBox=\"0 0 " << width << ' ' << height << "\" role=\"img\">\n"
           << "<title>Shadow play motor target trace</title><desc>Each panel compares commanded angle and limited target angle. This is command telemetry, not measured motor feedback.</desc>\n"
           << "<style>text{font-family:Arial,sans-serif;fill:#24344b;font-size:13px}.title{font-size:25px;font-weight:bold}.axis-title{font-size:17px;font-weight:bold}.small{font-size:12px}.grid{stroke:#dfe5ed;stroke-width:1}.command{stroke:#145cc5;stroke-width:2;fill:none}.target{stroke:#ca7909;stroke-width:1.6;stroke-dasharray:6 4;fill:none}</style>\n"
           << "<rect width=\"100%\" height=\"100%\" fill=\"#f8fafc\"/>\n"
           << "<text x=\"35\" y=\"40\" class=\"title\">Shadow play - motor target trace</text>\n"
           << "<text x=\"35\" y=\"67\">" << axes.size() << " axes | " << count << " samples | " << value_text(start)
           << " to " << value_text(end) << " s | Independent angle scale for each axis</text>\n"
           << "<path d=\"M35 92 H75\" class=\"command\"/><text x=\"85\" y=\"97\">Commanded angle (not measured)</text>\n"
           << "<path d=\"M380 92 H420\" class=\"target\"/><text x=\"430\" y=\"97\">Limited target before smoothing/rate limit</text>\n"
           << "<rect x=\"830\" y=\"83\" width=\"18\" height=\"14\" fill=\"#dbeafe\"/><text x=\"857\" y=\"97\">Returning to neutral</text>\n"
           << "<rect x=\"1090\" y=\"83\" width=\"18\" height=\"14\" fill=\"#e2e8f0\"/><text x=\"1117\" y=\"97\">No input</text>\n"
           << "<text x=\"35\" y=\"123\">Event lanes above each plot:</text><text x=\"250\" y=\"123\" style=\"fill:#dc2626\">I: input clamped</text>"
           << "<text x=\"420\" y=\"123\" style=\"fill:#9333ea\">A: angle limited</text><text x=\"590\" y=\"123\" style=\"fill:#a16207\">S: speed limited</text>\n"
           << "<text x=\"35\" y=\"148\" class=\"small\">Time is controller elapsed time. Missing intervals (&gt;3x median sample spacing) are left disconnected. Hover event bands for details.</text>\n";

    for (std::size_t axis_number = 0; axis_number < axes.size(); ++axis_number) {
        const auto& axis = axes[axis_number];
        const auto& samples = axis.samples;
        const double top = header_height + panel_height * static_cast<double>(axis_number);
        const double plot_top = top + 58.0;
        // Normalize before range arithmetic to avoid overflow for any finite CSV value.
        double scale = 1.0;
        for (const auto& sample : samples) scale = std::max({scale, std::abs(sample.angle), std::abs(sample.target)});
        double lo = samples.front().angle / scale, hi = lo;
        for (const auto& sample : samples) {
            lo = std::min({lo, sample.angle / scale, sample.target / scale});
            hi = std::max({hi, sample.angle / scale, sample.target / scale});
        }
        const double pad = hi > lo ? (hi - lo) * 0.08 : std::max(1.0 / scale, std::abs(lo) * 0.08);
        lo = std::max(-1.0, lo - pad);
        hi = std::min(1.0, hi + pad);
        if (hi <= lo) { lo = -1.0; hi = 1.0; }
        const auto y = [&](double angle) { return plot_top + plot_height * (hi - angle / scale) / (hi - lo); };
        const double interval = median_interval(axis);
        const auto connected = [&](std::size_t i) { return i > 0 && (samples[i].time - samples[i - 1].time) / 3.0 <= interval; };

        output << "<g><text x=\"35\" y=\"" << top + 18 << "\" class=\"axis-title\">" << xml(axis.id)
               << "</text><text x=\"650\" y=\"" << top + 18 << "\" class=\"small\">rod: " << xml(axis.rod)
               << " | " << samples.size() << " samples | median interval: " << value_text(interval) << " s</text>\n"
               << "<rect x=\"" << left << "\" y=\"" << plot_top << "\" width=\"" << plot_width << "\" height=\"" << plot_height << "\" fill=\"white\"/>\n";

        // Merge adjacent samples with an identical event state into one SVG band.
        for (int lane = -1; lane < 3; ++lane) {
            const auto key = [&](const Sample& sample) -> std::string {
                if (lane == -1) return sample.state == "no_input" || sample.state == "returning_to_neutral" ? sample.state : "";
                const bool active = lane == 0 ? sample.input_clamped : lane == 1 ? sample.angle_limited : sample.speed_limited;
                return active ? (lane == 0 ? "input_clamped" : lane == 1 ? "angle_limited" : "speed_limited") : "";
            };
            for (std::size_t i = 0; i < samples.size();) {
                const auto state = key(samples[i]);
                if (state.empty()) { ++i; continue; }
                std::size_t j = i + 1;
                while (j < samples.size() && connected(j) && key(samples[j]) == state) ++j;
                const double band_end = j < samples.size() && connected(j) ? samples[j].time : samples[j - 1].time;
                const char* color = lane == -1 ? (state == "no_input" ? "#e2e8f0" : "#dbeafe") : lane == 0 ? "#dc2626" : lane == 1 ? "#9333ea" : "#a16207";
                output << "<rect x=\"" << x(samples[i].time) << "\" y=\"" << (lane == -1 ? plot_top : top + 28.0 + lane * 8.0)
                       << "\" width=\"" << std::max(1.0, x(band_end) - x(samples[i].time)) << "\" height=\"" << (lane == -1 ? plot_height : 5.0)
                       << "\" fill=\"" << color << "\"><title>" << xml(state) << ": " << value_text(samples[i].time) << " - " << value_text(band_end) << " s</title></rect>\n";
                i = j;
            }
        }
        for (int lane = 0; lane < 3; ++lane) output << "<text x=\"78\" y=\"" << top + 33.0 + lane * 8.0 << "\" style=\"font-size:8px\">" << "IAS"[lane] << "</text>\n";
        for (int tick = 0; tick <= 4; ++tick) {
            const double yy = plot_top + plot_height * tick / 4.0;
            const double angle = (hi - (hi - lo) * tick / 4.0) * scale;
            output << "<path class=\"grid\" d=\"M" << left << ' ' << yy << " H" << left + plot_width << "\"/>"
                   << "<text x=\"85\" y=\"" << yy + 4.0 << "\" text-anchor=\"end\" class=\"small\">" << value_text(angle) << "</text>\n";
        }
        for (int tick = 0; tick <= 8; ++tick) {
            const double xx = left + plot_width * tick / 8.0;
            const double time = start + span * (static_cast<double>(tick) / 8.0);
            output << "<path class=\"grid\" d=\"M" << xx << ' ' << plot_top << " V" << plot_top + plot_height << "\"/>"
                   << "<text x=\"" << xx << "\" y=\"" << plot_top + plot_height + 20 << "\" text-anchor=\"middle\" class=\"small\">" << value_text(time) << "</text>\n";
        }
        for (int target = 1; target >= 0; --target) {
            output << "<path class=\"" << (target ? "target" : "command") << "\" d=\"";
            for (std::size_t i = 0; i < samples.size(); ++i) output << (connected(i) ? " L" : " M") << x(samples[i].time) << ' ' << y(target ? samples[i].target : samples[i].angle);
            output << "\"/>\n";
            // Isolated samples need a marker because a move-only path is invisible.
            for (std::size_t i = 0; i < samples.size(); ++i) {
                if (!connected(i) && (i + 1 == samples.size() || !connected(i + 1))) output << "<circle cx=\"" << x(samples[i].time) << "\" cy=\"" << y(target ? samples[i].target : samples[i].angle)
                    << "\" r=\"3\" fill=\"" << (target ? "#ca7909" : "#145cc5") << "\"/>\n";
            }
        }
        std::string modes;
        for (std::size_t i = 0; i < samples.size(); ++i) {
            if (!samples[i].mode.empty() && (i == 0 || samples[i].mode != samples[i - 1].mode)) {
                if (!modes.empty()) modes += "; ";
                modes += value_text(samples[i].time) + "s " + samples[i].mode;
            }
        }
        output << "<text x=\"" << left + plot_width / 2.0 << "\" y=\"" << top + 251.0 << "\" text-anchor=\"middle\">Controller time (s)</text>\n"
               << "<text x=\"" << left << "\" y=\"" << top + 269.0 << "\" class=\"small\">Angle (degrees)";
        if (!modes.empty()) output << " | modes: " << xml(modes);
        output << "</text></g>\n";
    }
    output << "</svg>\n";
    output.close();
    if (!output) throw std::runtime_error("Failed while writing SVG output: " + path);
}
}  // namespace

int main(int argc, char** argv) {
    if (argc == 2 && std::string(argv[1]) == "--help") {
        std::cout << "Usage: trace_preview INPUT.csv OUTPUT.svg\nPlots simulated/commanded angles, not physical motor feedback.\n";
        return 0;
    }
    if (argc != 3) {
        std::cerr << "Usage: trace_preview INPUT.csv OUTPUT.svg\n";
        return 2;
    }
    try {
        const std::string input(argv[1]);
        const std::string output(argv[2]);
        if (input == output) throw std::runtime_error("Input CSV and output SVG must be different files");
        const auto axes = read_trace(input);
        write_svg(output, axes);
        std::cout << "Wrote " << output << " (" << axes.size() << " axes). Open it in a browser.\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "trace_preview: " << error.what() << '\n';
        return 1;
    }
}
