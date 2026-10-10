#include "shadow/calibration_csv.hpp"

#include <cmath>
#include <fstream>
#include <stdexcept>

namespace shadow {
namespace {
const char* kHeader =
    "axis_id,rod,neutral_deg,min_deg,max_deg,gain_x_deg,gain_y_deg,max_speed_deg_s,smoothing_tau_s";

std::string trim(const std::string& value) {
    const auto first = value.find_first_not_of(" \t\r\n");
    if (first == std::string::npos) return {};
    const auto last = value.find_last_not_of(" \t\r\n");
    return value.substr(first, last - first + 1);
}

std::vector<std::string> split(const std::string& line) {
    std::vector<std::string> fields;
    std::size_t start = 0;
    while (true) {
        const auto comma = line.find(',', start);
        fields.push_back(trim(line.substr(start, comma == std::string::npos
                                                    ? comma : comma - start)));
        if (comma == std::string::npos) return fields;
        start = comma + 1;
    }
}

double number(const std::string& value) {
    std::size_t consumed = 0;
    const double result = std::stod(value, &consumed);
    if (consumed != value.size() || !std::isfinite(result)) {
        throw std::invalid_argument("invalid finite number: " + value);
    }
    return result;
}
}  // namespace

std::vector<AxisCalibration> read_calibration_csv(std::istream& input) {
    std::vector<AxisCalibration> axes;
    std::string line;
    std::size_t line_number = 0;
    bool header_seen = false;
    const auto expected_header = split(kHeader);
    while (std::getline(input, line)) {
        ++line_number;
        if (line_number == 1 && line.compare(0, 3, "\xEF\xBB\xBF") == 0) line.erase(0, 3);
        line = trim(line);
        if (line.empty() || line.front() == '#') continue;
        try {
            const auto fields = split(line);
            if (!header_seen) {
                if (fields != expected_header) throw std::invalid_argument("unexpected CSV header");
                header_seen = true;
                continue;
            }
            if (fields.size() != expected_header.size()) {
                throw std::invalid_argument("expected exactly 9 columns");
            }
            axes.push_back({fields[0], parse_rod_name(fields[1]), number(fields[2]),
                            number(fields[3]), number(fields[4]), number(fields[5]),
                            number(fields[6]), number(fields[7]), number(fields[8])});
        } catch (const std::exception& error) {
            throw std::invalid_argument("calibration CSV line " + std::to_string(line_number) +
                                        ": " + error.what());
        }
    }
    if (input.bad()) throw std::runtime_error("failed reading calibration CSV");
    if (!header_seen) throw std::invalid_argument("calibration CSV has no header");
    validate_calibrations(axes);
    return axes;
}

std::vector<AxisCalibration> load_calibration_csv(const std::string& path) {
    std::ifstream input(path);
    if (!input) throw std::runtime_error("cannot open calibration CSV: " + path);
    return read_calibration_csv(input);
}

}  // namespace shadow
