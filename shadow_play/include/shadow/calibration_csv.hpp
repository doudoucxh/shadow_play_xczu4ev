#pragma once

#include "shadow/motion_mapper.hpp"

#include <istream>
#include <string>
#include <vector>

namespace shadow {

// Strict, unquoted CSV; blank lines and lines beginning with # are ignored.
// Duplicate IDs, missing columns, invalid names/numbers and unsafe ranges fail.
std::vector<AxisCalibration> read_calibration_csv(std::istream& input);
std::vector<AxisCalibration> load_calibration_csv(const std::string& path);

}  // namespace shadow
