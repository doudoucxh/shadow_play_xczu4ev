#include "shadow/capture_geometry.hpp"

#include <array>
#include <cmath>
#include <functional>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace {
using Quad = std::array<cv::Point2f, 4>;
constexpr double width_mm = 600.0;
constexpr double height_mm = 400.0;
const Quad stage_corners{{{0.0f, 0.0f}, {600.0f, 0.0f},
                          {600.0f, 400.0f}, {0.0f, 400.0f}}};

void require(bool condition, const std::string& message) {
    if (!condition) throw std::runtime_error(message);
}

void near(double actual, double expected, double tolerance = 0.002) {
    if (!std::isfinite(actual) || std::abs(actual - expected) > tolerance) {
        throw std::runtime_error("expected " + std::to_string(expected) +
                                 ", got " + std::to_string(actual));
    }
}

void near_point(cv::Point2d actual, cv::Point2d expected, double tolerance = 0.002) {
    near(actual.x, expected.x, tolerance);
    near(actual.y, expected.y, tolerance);
}

template <typename Function>
void rejects(Function function) {
    bool rejected = false;
    try { function(); } catch (const std::exception&) { rejected = true; }
    require(rejected, "invalid input was not rejected");
}

// Independent camera models supply known answers without using the production
// matrix, its inverse, or OpenCV's perspective transform to compute expectations.
cv::Point2d camera_a(cv::Point2d stage) {
    const double denominator = 1.0 + 0.0005 * stage.x + 0.00025 * stage.y;
    return {(0.8 * stage.x + 0.2 * stage.y + 120.0) / denominator,
            (0.12 * stage.x - 0.8 * stage.y + 550.0) / denominator};
}

cv::Point2d camera_b(cv::Point2d stage) {
    const double denominator = 1.0 - 0.0002 * stage.x + 0.0004 * stage.y;
    return {(1.05 * stage.x - 0.15 * stage.y + 180.0) / denominator,
            (-0.18 * stage.x - 0.95 * stage.y + 610.0) / denominator};
}

Quad camera_corners(cv::Point2d (*camera)(cv::Point2d)) {
    Quad result{};
    for (std::size_t i = 0; i < result.size(); ++i) {
        const auto pixel = camera(stage_corners[i]);
        result[i] = {static_cast<float>(pixel.x), static_cast<float>(pixel.y)};
    }
    return result;
}

void test_rear_origin_and_four_corners() {
    const auto pixels = camera_corners(camera_a);
    shadow::CaptureGeometry geometry;
    geometry.calibrate(pixels, stage_corners, width_mm, height_mm, {800, 600});
    require(geometry.valid(), "valid camera quadrilateral was rejected");
    for (std::size_t i = 0; i < pixels.size(); ++i) {
        require(geometry.contains_pixel(pixels[i]), "reference corner is outside region");
        near_point(geometry.to_stage(pixels[i]), stage_corners[i]);
        near_point(geometry.to_pixel(stage_corners[i]), pixels[i]);
    }
    // Rear lower-left is zero; moving right raises x and moving up raises y,
    // even though the corresponding camera image has y increasing downward.
    near_point(geometry.to_stage(pixels[0]), {0.0, 0.0});
    near_point(geometry.to_stage(pixels[1]), {width_mm, 0.0});
    near_point(geometry.to_stage(pixels[3]), {0.0, height_mm});
    require(pixels[3].y < pixels[0].y, "fixture does not exercise camera y reversal");
}

void test_known_interior_projection_for_two_skew_views() {
    shadow::CaptureGeometry geometry;
    geometry.calibrate(camera_corners(camera_a), stage_corners,
                       width_mm, height_mm, {800, 600});
    // These pixel coordinates are calculated analytically for stage (240,160).
    near_point(geometry.to_stage({296.551724137931, 388.620689655172}), {240.0, 160.0});
    near_point(geometry.to_pixel({240.0, 160.0}), {296.551724137931, 388.620689655172});

    geometry.calibrate(camera_corners(camera_b), stage_corners,
                       width_mm, height_mm, {1280, 800});
    near_point(geometry.to_stage({401.574803149606, 408.267716535433}), {240.0, 160.0});
    near_point(geometry.to_pixel({240.0, 160.0}), {401.574803149606, 408.267716535433});
    near_point(geometry.to_stage(camera_b({510.0, 320.0})), {510.0, 320.0});
    near_point(geometry.to_stage(camera_b({75.0, 280.0})), {75.0, 280.0});
}

void test_roundtrip_inside_region() {
    for (auto camera : {camera_a, camera_b}) {
        shadow::CaptureGeometry geometry;
        geometry.calibrate(camera_corners(camera), stage_corners,
                           width_mm, height_mm, {1280, 800});
        for (auto stage : std::array<cv::Point2d, 5>{{{50.0, 50.0}, {300.0, 200.0},
                                                     {550.0, 350.0}, {75.0, 280.0},
                                                     {510.0, 320.0}}}) {
            const auto expected_pixel = camera(stage);
            require(geometry.contains_pixel(expected_pixel), "interior point rejected");
            near_point(geometry.to_stage(expected_pixel), stage);
            near_point(geometry.to_stage(geometry.to_pixel(stage)), stage);
            near_point(geometry.to_pixel(geometry.to_stage(expected_pixel)), expected_pixel);
        }
    }
}

void test_rejects_collinear_and_crossed_reference_points() {
    shadow::CaptureGeometry geometry;
    const Quad collinear{{{100.0f, 400.0f}, {200.0f, 350.0f},
                           {300.0f, 300.0f}, {400.0f, 250.0f}}};
    rejects([&] { geometry.calibrate(collinear, stage_corners,
                                     width_mm, height_mm, {800, 600}); });
    require(!geometry.valid(), "collinear points left calibration valid");
    auto crossed = camera_corners(camera_a);
    std::swap(crossed[1], crossed[2]);
    rejects([&] { geometry.calibrate(crossed, stage_corners,
                                     width_mm, height_mm, {800, 600}); });
    require(!geometry.valid(), "self-crossing points left calibration valid");
}

void test_reference_points_must_be_in_image() {
    shadow::CaptureGeometry geometry;
    for (const auto outside : std::array<cv::Point2f, 4>{{{-1.0f, 550.0f}, {800.0f, 550.0f},
                                                         {120.0f, -1.0f}, {120.0f, 600.0f}}}) {
        auto pixels = camera_corners(camera_a);
        pixels[0] = outside;
        rejects([&] { geometry.calibrate(pixels, stage_corners,
                                         width_mm, height_mm, {800, 600}); });
        require(!geometry.valid(), "outside reference point left calibration valid");
    }
}

void test_contains_rejects_letterbox_and_outside_quadrilateral() {
    shadow::CaptureGeometry geometry;
    geometry.calibrate(camera_corners(camera_a), stage_corners,
                       width_mm, height_mm, {800, 600});
    // A widget letterbox click converts to negative or past-edge image coords.
    // Contains must also reject in-image clicks outside the calibrated stage.
    for (const auto pixel : std::array<cv::Point2d, 7>{{{-20.0, 300.0}, {820.0, 300.0},
                                                      {400.0, -20.0}, {400.0, 620.0},
                                                      {800.0, 300.0}, {400.0, 600.0},
                                                      {20.0, 20.0}}}) {
        require(!geometry.contains_pixel(pixel), "letterbox/outside click was accepted");
        rejects([&] { geometry.to_stage(pixel); });
    }
}

void test_frame_size_and_calibration_lifecycle() {
    shadow::CaptureGeometry geometry;
    require(!geometry.valid(), "new geometry is already calibrated");
    require(!geometry.contains_pixel({300.0, 300.0}), "uncalibrated geometry contains a point");
    rejects([&] { geometry.to_stage({300.0, 300.0}); });
    rejects([&] { geometry.to_pixel({300.0, 200.0}); });

    const auto first = camera_corners(camera_a);
    geometry.calibrate(first, stage_corners, width_mm, height_mm, {800, 600});
    require(geometry.frame_size() == cv::Size(800, 600), "camera frame size was not retained");
    require(geometry.pixels() == first, "reference pixels were not retained");
    geometry.clear();
    require(!geometry.valid(), "clear retained calibration");
    rejects([&] { geometry.to_stage(camera_a({300.0, 200.0})); });

    geometry.calibrate(camera_corners(camera_b), stage_corners,
                       width_mm, height_mm, {1280, 800});
    require(geometry.frame_size() == cv::Size(1280, 800), "recalibration kept the old frame size");
    auto invalid = camera_corners(camera_b);
    invalid[0].x = std::numeric_limits<float>::quiet_NaN();
    rejects([&] { geometry.calibrate(invalid, stage_corners,
                                     width_mm, height_mm, {1280, 800}); });
    require(!geometry.valid(), "failed recalibration retained an old active projection");
}

void test_rectified_coordinates_and_corners() {
    const cv::Size display_size(901, 501);
    const std::array<cv::Point2d, 4> display_corners{{{0, 500}, {900, 500},
                                                    {900, 0}, {0, 0}}};
    for (auto camera : {camera_a, camera_b}) {
        shadow::CaptureGeometry geometry;
        const auto pixels = camera_corners(camera);
        geometry.calibrate(pixels, stage_corners, width_mm, height_mm, {1280, 800});
        for (std::size_t i = 0; i < pixels.size(); ++i) {
            near_point(geometry.display_to_pixel(display_corners[i], display_size), pixels[i]);
            near_point(geometry.pixel_to_display(pixels[i], display_size), display_corners[i]);
        }
        // x scales by 900/600; display y is reversed and scales by 500/400.
        near_point(geometry.pixel_to_display(camera({240, 160}), display_size), {360, 300});
        near_point(geometry.display_to_pixel({360, 300}, display_size), camera({240, 160}));
        near_point(geometry.display_to_pixel({450, 250}, display_size), camera({300, 200}));
        const auto pixel = camera({75, 280});
        near_point(geometry.display_to_pixel(geometry.pixel_to_display(pixel, display_size), display_size), pixel);
    }
}

void test_rectified_image_samples_and_preserves_source() {
    shadow::CaptureGeometry geometry;
    geometry.calibrate(camera_corners(camera_a), stage_corners, width_mm, height_mm, {800, 600});
    // A two-channel camera image encodes original x/y at every source pixel.
    // Its rectified values must match an independently known projective camera,
    // so this tests warp direction and y orientation as well as coordinate APIs.
    cv::Mat frame(600, 800, CV_32FC2);
    for (int y = 0; y < frame.rows; ++y)
        for (int x = 0; x < frame.cols; ++x)
            frame.at<cv::Vec2f>(y, x) = {static_cast<float>(x), static_cast<float>(y)};
    const auto original = frame.clone();
    const auto display = geometry.rectify(frame, {601, 401});
    require(display.size() == cv::Size(601, 401) && display.type() == frame.type(),
            "rectify returned the wrong dimensions or image type");
    for (auto display_point : std::array<cv::Point, 5>{{{0, 400}, {600, 400}, {600, 0},
                                                       {0, 0}, {240, 240}}}) {
        const auto expected = camera_a({static_cast<double>(display_point.x),
                                       400.0-display_point.y});
        const auto actual = display.at<cv::Vec2f>(display_point.y, display_point.x);
        // OpenCV INTER_LINEAR uses interpolation weights with 1/32-pixel steps.
        near_point({actual[0], actual[1]}, expected, 0.04);
    }
    require(cv::norm(frame, original, cv::NORM_INF) == 0, "rectification modified the evidence frame");
    require(display.data != frame.data, "rectification aliases the original image");
}

void test_rectification_input_validation() {
    shadow::CaptureGeometry geometry;
    const cv::Mat source(600, 800, CV_8UC3, cv::Scalar(10, 20, 30));
    rejects([&] { geometry.rectify(source, {601, 401}); });
    rejects([&] { geometry.display_to_pixel({100, 100}, {601, 401}); });
    rejects([&] { geometry.pixel_to_display({300, 300}, {601, 401}); });
    geometry.calibrate(camera_corners(camera_a), stage_corners, width_mm, height_mm, {800, 600});
    for (auto size : std::array<cv::Size, 4>{{{0, 401}, {601, 0}, {1, 401}, {601, 1}}}) {
        rejects([&] { geometry.rectify(source, size); });
        rejects([&] { geometry.display_to_pixel({0, 0}, size); });
        rejects([&] { geometry.pixel_to_display(camera_a({240, 160}), size); });
    }
    rejects([&] { geometry.rectify(cv::Mat(), {601, 401}); });
    rejects([&] { geometry.rectify(cv::Mat(599, 800, CV_8UC3), {601, 401}); });
    rejects([&] { geometry.rectify(cv::Mat(600, 801, CV_8UC3), {601, 401}); });
    for (auto point : std::array<cv::Point2d, 6>{{{-0.1, 100}, {600.1, 100}, {100, -0.1},
                                                {100, 400.1}, {601, 400},
                                                {std::numeric_limits<double>::quiet_NaN(), 100}}}) {
        rejects([&] { geometry.display_to_pixel(point, {601, 401}); });
    }
    for (auto point : std::array<cv::Point2d, 4>{{{-1, 300}, {800, 300}, {300, 600}, {20, 20}}})
        rejects([&] { geometry.pixel_to_display(point, {601, 401}); });
    geometry.clear();
    rejects([&] { geometry.rectify(source, {601, 401}); });
}

void test_inner_markers_preserve_full_stage_preview_and_measurement_bounds() {
    // Markers at 100..500 x 80..320 mm are reference positions, not stage edges.
    const Quad inner_mm{{{100, 80}, {500, 80}, {500, 320}, {100, 320}}};
    Quad pixels{};
    for (std::size_t i = 0; i < pixels.size(); ++i) {
        const auto pixel = camera_a(inner_mm[i]);
        pixels[i] = {static_cast<float>(pixel.x), static_cast<float>(pixel.y)};
    }
    shadow::CaptureGeometry geometry;
    geometry.calibrate(pixels, inner_mm, width_mm, height_mm, {800, 600});
    near_point(geometry.display_to_pixel({0, 400}, {601, 401}), camera_a({0, 0}));
    near_point(geometry.display_to_pixel({600, 0}, {601, 401}), camera_a({600, 400}));
    near_point(geometry.pixel_to_display(camera_a({240, 160}), {601, 401}), {240, 240});
    // Full-stage preview extrapolates, but measured clicks still use only the
    // reference polygon. This prevents confusing inner marks with stage edges.
    const auto beyond_markers = geometry.display_to_pixel({50, 350}, {601, 401});
    require(!geometry.contains_pixel(beyond_markers), "inner reference polygon was expanded by the preview");
    rejects([&] { geometry.to_stage(beyond_markers); });
    rejects([&] { geometry.pixel_to_display(beyond_markers, {601, 401}); });
    require(!geometry.rectify(cv::Mat(600, 800, CV_8UC3, cv::Scalar(10, 20, 30)), {601, 401}).empty(),
            "inner reference marks cannot rectify the whole stage");

    // The physical stage can extend beyond the camera. Show those pixels black
    // in the preview, while rejecting clicks that have no source-image pixel.
    geometry.calibrate(pixels, inner_mm, 1200, 800, {800, 600});
    const auto oversized = geometry.rectify(cv::Mat(600, 800, CV_8UC3, cv::Scalar(255, 255, 255)), {601, 401});
    require(oversized.at<cv::Vec3b>(0, 0) == cv::Vec3b(0, 0, 0),
            "stage beyond the camera should use black border pixels");
    rejects([&] { geometry.display_to_pixel({0, 0}, {601, 401}); });

    auto outside_mm = inner_mm; outside_mm[0].x = -1;
    rejects([&] { geometry.calibrate(pixels, outside_mm, width_mm, height_mm, {800, 600}); });
}

void test_fractional_stage_edges() {
    const double width = 600.1, height = 400.2;
    const Quad millimetres{{{0, 0}, {static_cast<float>(width), 0},
                            {static_cast<float>(width), static_cast<float>(height)},
                            {0, static_cast<float>(height)}}};
    Quad pixels{};
    for (std::size_t i = 0; i < pixels.size(); ++i) {
        const auto pixel = camera_a(millimetres[i]);
        pixels[i] = {static_cast<float>(pixel.x), static_cast<float>(pixel.y)};
    }
    shadow::CaptureGeometry geometry;
    geometry.calibrate(pixels, millimetres, width, height, {800, 600});
    near_point(geometry.display_to_pixel({600, 0}, {601, 401}), camera_a({width, height}));
    near_point(geometry.pixel_to_display(pixels[2], {601, 401}), {600, 0});
}
}  // namespace

int main() {
    const std::vector<std::pair<std::string, std::function<void()>>> tests = {
        {"rear origin and four corners", test_rear_origin_and_four_corners},
        {"known interior projection for two skew views", test_known_interior_projection_for_two_skew_views},
        {"stage and pixel roundtrip", test_roundtrip_inside_region},
        {"collinear and self-crossing references", test_rejects_collinear_and_crossed_reference_points},
        {"reference points outside image", test_reference_points_must_be_in_image},
        {"letterbox and outside-region click rejection", test_contains_rejects_letterbox_and_outside_quadrilateral},
        {"frame size and calibration lifecycle", test_frame_size_and_calibration_lifecycle},
        {"rectified coordinates and four corners", test_rectified_coordinates_and_corners},
        {"rectified image projection and original evidence", test_rectified_image_samples_and_preserves_source},
        {"rectification input validation", test_rectification_input_validation},
        {"inner marks and full-stage preview", test_inner_markers_preserve_full_stage_preview_and_measurement_bounds},
        {"fractional stage dimensions", test_fractional_stage_edges}
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
