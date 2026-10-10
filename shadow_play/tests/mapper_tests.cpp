#include "shadow/calibration_csv.hpp"
#include "shadow/motion_mapper.hpp"

#include <cmath>
#include <functional>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace {
using namespace shadow;

void require(bool condition, const std::string& message) {
    if (!condition) throw std::runtime_error(message);
}

void near(double actual, double expected, double tolerance = 1e-9) {
    if (!std::isfinite(actual) || std::abs(actual - expected) > tolerance) {
        throw std::runtime_error("expected " + std::to_string(expected) +
                                 ", got " + std::to_string(actual));
    }
}

template <typename Function>
void rejects(Function function) {
    bool rejected = false;
    try { function(); } catch (const std::exception&) { rejected = true; }
    require(rejected, "invalid input was not rejected");
}

AxisCalibration axis(const std::string& id = "body_axis",
                     RodId rod = RodId::WusongNeck) {
    return {id, rod, 90.0, 30.0, 150.0, 30.0, 20.0, 10000.0, 0.0};
}

ShadowPose pose(double x, double y = 0.0, RodId rod = RodId::WusongNeck) {
    ShadowPose result;
    result.at(rod) = {x, y, true};
    return result;
}

const std::string csv_header =
    "axis_id,rod,neutral_deg,min_deg,max_deg,gain_x_deg,gain_y_deg,max_speed_deg_s,smoothing_tau_s\n";
const std::string csv_row = "a,wusong_neck,90,30,150,30,-20,60,0.08\n";

void test_center_and_axis_count() {
    MotionMapper mapper({axis()}, {90.0});
    require(mapper.submit_pose(pose(0.0), 0.0) == 1, "wrong accepted rod count");
    const auto out = mapper.step(0.02);
    require(out.size() == 1 && out[0].axis_id == "body_axis", "assumed fixed axis count");
    near(out[0].angle_deg, 90.0);
    require(out[0].input_state == InputState::TrackingOrHolding, "center not tracked");
}

void test_signed_mixed_mapping() {
    auto a = axis();
    a.gain_y_deg = -10.0;
    auto b = a;
    b.axis_id = "reverse";
    b.gain_x_deg = -30.0;
    MotionMapper mapper({a, b}, {90.0, 90.0});
    mapper.submit_pose(pose(0.5, -0.5), 0.0);
    const auto out = mapper.step(0.02);
    near(out[0].angle_deg, 110.0);
    near(out[1].angle_deg, 80.0);
}

void test_rod_routing() {
    MotionMapper mapper({axis("body"), axis("tail", RodId::TigerTail)}, {90.0, 90.0});
    mapper.submit_pose(pose(1.0, 0.0, RodId::TigerTail), 0.0);
    const auto out = mapper.step(0.02);
    near(out[0].angle_deg, 90.0);
    near(out[1].angle_deg, 120.0);
    require(out[0].input_state == InputState::NoInput, "unprovided rod became active");
}

void test_input_clipping() {
    MotionMapper mapper({axis()}, {90.0});
    mapper.submit_pose(pose(2.0, -3.0), 0.0);
    const auto out = mapper.step(0.02);
    near(out[0].angle_deg, 100.0);
    require(out[0].input_clamped, "input clamp not reported");
}

void test_angle_limits_both_directions() {
    auto a = axis();
    a.gain_x_deg = 1000.0;
    MotionMapper mapper({a}, {90.0});
    mapper.submit_pose(pose(1.0), 0.0);
    auto out = mapper.step(0.02);
    near(out[0].angle_deg, 150.0);
    require(out[0].angle_limited, "upper clamp not reported");
    mapper.submit_pose(pose(-1.0), 0.04);
    out = mapper.step(0.04);
    near(out[0].angle_deg, 30.0);
    require(out[0].angle_limited, "lower clamp not reported");
}

void test_rate_limit_and_irregular_time() {
    auto a = axis();
    a.max_speed_deg_s = 10.0;
    MotionMapper mapper({a}, {90.0});
    mapper.submit_pose(pose(1.0), 0.0);
    auto out = mapper.step(0.02);
    near(out[0].angle_deg, 90.2);
    require(out[0].speed_limited, "rate limit not reported");
    out = mapper.step(0.03);
    near(out[0].angle_deg, 90.3);
    mapper.submit_pose(pose(-1.0), 0.05);
    out = mapper.step(0.05);
    near(out[0].angle_deg, 90.1);
}

void test_stall_does_not_catch_up() {
    auto a = axis();
    a.max_speed_deg_s = 10.0;
    MotionMapper mapper({a}, {90.0});
    mapper.submit_pose(pose(1.0), 10.0);
    auto out = mapper.step(10.0);
    near(out[0].angle_deg, 90.5);  // at most 0.05 s of movement after a 10 s stall
    out = mapper.step(10.0);
    near(out[0].angle_deg, 90.5);  // duplicate tick cannot move again
}

void test_exponential_smoothing() {
    auto a = axis();
    a.smoothing_tau_s = 0.1;
    MotionMapper mapper({a}, {90.0});
    mapper.submit_pose(pose(1.0), 0.0);
    near(mapper.step(0.02)[0].angle_deg, 90.0 + 30.0 * (1.0 - std::exp(-0.2)));
}

void test_timeout_hold_then_neutral() {
    MotionMapper mapper({axis()}, {90.0});
    mapper.submit_pose(pose(1.0), 0.0);
    near(mapper.step(0.02)[0].angle_deg, 120.0);
    auto out = mapper.step(0.3);
    near(out[0].angle_deg, 120.0);
    require(out[0].input_state == InputState::TrackingOrHolding, "hold expired early");
    out = mapper.step(0.4);
    near(out[0].angle_deg, 90.0);
    require(out[0].input_state == InputState::ReturningToNeutral, "timeout missed");
    mapper.submit_pose(pose(-1.0), 0.42);
    out = mapper.step(0.42);
    near(out[0].angle_deg, 60.0);
    require(out[0].input_state == InputState::TrackingOrHolding, "recovery failed");
}

void test_invalid_samples_do_not_refresh_age() {
    MotionMapper mapper({axis()}, {90.0});
    mapper.submit_pose(pose(1.0), 0.0);
    mapper.step(0.02);
    auto invalid = pose(std::numeric_limits<double>::quiet_NaN());
    require(mapper.submit_pose(invalid, 0.1) == 0, "NaN accepted");
    invalid = pose(std::numeric_limits<double>::infinity());
    require(mapper.submit_pose(invalid, 0.2) == 0, "infinity accepted");
    invalid = pose(-1.0);
    invalid.at(RodId::WusongNeck).valid = false;
    require(mapper.submit_pose(invalid, 0.29) == 0, "invalid flag ignored");
    const auto out = mapper.step(0.4);
    near(out[0].angle_deg, 90.0);
    require(out[0].input_state == InputState::ReturningToNeutral, "bad sample refreshed age");
}

void test_each_rod_has_independent_age() {
    MotionMapper mapper({axis("body"), axis("left", RodId::WusongLeft)}, {90.0, 90.0});
    mapper.submit_pose(pose(1.0), 0.0);
    mapper.step(0.02);
    mapper.submit_pose(pose(1.0, 0.0, RodId::WusongLeft), 0.2);
    const auto out = mapper.step(0.4);
    require(out[0].input_state == InputState::ReturningToNeutral, "body wrongly refreshed");
    require(out[1].input_state == InputState::TrackingOrHolding, "left lost fresh input");
}

void test_clear_inputs_and_smooth_return() {
    auto a = axis();
    a.smoothing_tau_s = 0.1;
    a.max_speed_deg_s = 10.0;
    MotionMapper mapper({a}, {90.0});
    mapper.submit_pose(pose(1.0), 0.0);
    const double previous = mapper.step(0.02)[0].angle_deg;
    mapper.clear_inputs(0.03);
    const auto out = mapper.step(0.04);
    require(out[0].input_state == InputState::NoInput, "mode switch retained old input");
    require(out[0].angle_deg < previous && out[0].angle_deg >= 90.0,
            "return overshot or continued outward");
    require(previous - out[0].angle_deg <= 0.2 + 1e-9, "return exceeded rate limit");
}

void test_initial_command_is_respected() {
    auto a = axis();
    a.max_speed_deg_s = 10.0;
    MotionMapper mapper({a}, {110.0});
    near(mapper.step(0.0)[0].angle_deg, 110.0);
    near(mapper.step(0.02)[0].angle_deg, 109.8);
    rejects([&] { MotionMapper invalid({a}, {}); });
    rejects([&] { MotionMapper invalid({a}, {151.0}); });
    rejects([&] { MotionMapper invalid({a}, {std::numeric_limits<double>::quiet_NaN()}); });
}

void test_time_validation_is_atomic() {
    MotionMapper mapper({axis()}, {90.0}, {}, 1.0);
    mapper.submit_pose(pose(1.0), 1.0);
    near(mapper.step(1.02)[0].angle_deg, 120.0);
    rejects([&] { mapper.submit_pose(pose(-1.0), 0.9); });
    rejects([&] { mapper.step(0.9); });
    rejects([&] { mapper.clear_inputs(0.9); });
    rejects([&] { mapper.step(std::numeric_limits<double>::infinity()); });
    near(mapper.step(1.04)[0].angle_deg, 120.0);
}

void test_invalid_calibration_and_options() {
    rejects([] { MotionMapper invalid({}, {}); });
    rejects([] { validate_calibrations({axis(), axis()}); });
    auto a = axis();
    a.min_deg = 100.0;
    rejects([&] { validate_calibrations({a}); });
    a = axis(); a.min_deg = a.max_deg;
    rejects([&] { validate_calibrations({a}); });
    a = axis(); a.max_speed_deg_s = 0.0;
    rejects([&] { validate_calibrations({a}); });
    a = axis(); a.smoothing_tau_s = -0.01;
    rejects([&] { validate_calibrations({a}); });
    a = axis(); a.gain_x_deg = std::numeric_limits<double>::infinity();
    rejects([&] { validate_calibrations({a}); });
    a = axis(); a.rod = RodId::Count;
    rejects([&] { validate_calibrations({a}); });
    a = axis(); a.axis_id = "contains,comma";
    rejects([&] { validate_calibrations({a}); });
    a = axis(); a.gain_x_deg = std::numeric_limits<double>::max();
    a.gain_y_deg = std::numeric_limits<double>::max();
    rejects([&] { validate_calibrations({a}); });
    rejects([] { MotionMapper invalid({axis()}, {90.0}, {-1.0, 0.05}); });
    rejects([] { MotionMapper invalid({axis()}, {90.0}, {0.3, 0.0}); });
    rejects([] { MotionMapper invalid({axis()}, {90.0}, {}, -1.0); });
}

void test_screen_conversion_and_bad_rod() {
    auto target = from_unit_screen(0.0, 1.0);
    near(target.x, -1.0); near(target.y, -1.0);
    target = from_unit_screen(1.0, 0.0);
    near(target.x, 1.0); near(target.y, 1.0);
    target = from_unit_screen(0.5, 0.5);
    near(target.x, 0.0); near(target.y, 0.0);
    require(!from_unit_screen(0.5, 0.5, false).valid, "validity ignored");
    require(!from_unit_screen(std::numeric_limits<double>::infinity(), 0.5).valid,
            "non-finite screen coordinate accepted");
    require(parse_rod_name("tiger_tail") == RodId::TigerTail, "rod parse failed");
    rejects([] { parse_rod_name("typo"); });
    rejects([] { ShadowPose p; p.at(RodId::Count); });
}

void test_csv_valid_and_missing_file() {
    std::istringstream csv("\xEF\xBB\xBF# simulator\r\n\n" + csv_header + csv_row);
    const auto axes = read_calibration_csv(csv);
    require(axes.size() == 1 && axes[0].axis_id == "a", "CSV axis missing");
    near(axes[0].gain_y_deg, -20.0);
    near(axes[0].smoothing_tau_s, 0.08);
    rejects([] { load_calibration_csv("__missing_calibration_97c3__.csv"); });
}

void test_csv_rejects_bad_data() {
    const std::vector<std::string> bad = {
        "", "wrong,header\n" + csv_row, csv_header,
        csv_header + "a,wusong_neck,90,30,150,30,-20,60\n",
        csv_header + "a,wusong_neck,90,30,150,30,-20,60,0,\n",
        csv_header + "a,wusong_neck,90deg,30,150,30,-20,60,0\n",
        csv_header + "a,wusong_neck,nan,30,150,30,-20,60,0\n",
        csv_header + "a,wusong_neck,90,30,150,30,-20,inf,0\n",
        csv_header + "a,unknown,90,30,150,30,-20,60,0\n",
        csv_header + csv_row + csv_row,
        csv_header + "a,wusong_neck,200,30,150,30,-20,60,0\n"
    };
    for (const auto& content : bad) {
        rejects([&] { std::istringstream csv(content); read_calibration_csv(csv); });
    }
}

void test_long_trace_stays_bounded() {
    auto a = axis();
    a.max_speed_deg_s = 40.0;
    a.smoothing_tau_s = 0.07;
    MotionMapper mapper({a}, {90.0});
    double previous = 90.0;
    double previous_t = 0.0;
    for (int i = 0; i < 3000; ++i) {
        const double t = i * 0.017;
        if (i % 41 < 25) mapper.submit_pose(pose(2.5 * std::sin(t * 9), std::cos(t * 7)), t);
        const auto out = mapper.step(t);
        const double value = out[0].angle_deg;
        require(std::isfinite(value) && value >= a.min_deg && value <= a.max_deg,
                "long trace violated angle bounds");
        require(std::abs(value - previous) <= a.max_speed_deg_s * (t - previous_t) + 1e-8,
                "long trace violated rate bounds");
        previous = value;
        previous_t = t;
    }
}
}  // namespace

int main() {
    const std::vector<std::pair<std::string, std::function<void()>>> tests = {
        {"center and configurable axis count", test_center_and_axis_count},
        {"signed x/y mapping", test_signed_mixed_mapping},
        {"independent rod routing", test_rod_routing},
        {"coordinate clipping", test_input_clipping},
        {"angle limits", test_angle_limits_both_directions},
        {"rate limits with irregular time", test_rate_limit_and_irregular_time},
        {"stall and duplicate tick", test_stall_does_not_catch_up},
        {"exponential smoothing", test_exponential_smoothing},
        {"timeout hold, return and recovery", test_timeout_hold_then_neutral},
        {"invalid samples do not refresh age", test_invalid_samples_do_not_refresh_age},
        {"per-rod input age", test_each_rod_has_independent_age},
        {"mode clear and smooth neutral return", test_clear_inputs_and_smooth_return},
        {"explicit initial command", test_initial_command_is_respected},
        {"monotonic time and atomic rejection", test_time_validation_is_atomic},
        {"calibration validation", test_invalid_calibration_and_options},
        {"screen conversion", test_screen_conversion_and_bad_rod},
        {"valid calibration CSV", test_csv_valid_and_missing_file},
        {"malformed calibration CSV", test_csv_rejects_bad_data},
        {"long trace motion bounds", test_long_trace_stays_bounded}
    };
    int failed = 0;
    for (const auto& test : tests) {
        try {
            test.second();
            std::cout << "PASS " << test.first << '\n';
        } catch (const std::exception& error) {
            ++failed;
            std::cerr << "FAIL " << test.first << ": " << error.what() << '\n';
        }
    }
    std::cout << tests.size() - static_cast<std::size_t>(failed) << '/' << tests.size()
              << " tests passed\n";
    return failed == 0 ? 0 : 1;
}
