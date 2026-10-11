// Image-only stage reference: no serial, network, PWM or motion backend.
#include "shadow/capture_geometry.hpp"
#include <nlohmann/json.hpp>
#include <opencv2/imgcodecs.hpp>
#include <opencv2/imgproc.hpp>
#include <algorithm>
#include <array>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

using Json = nlohmann::json;
namespace fs = std::filesystem;

namespace {
cv::Point2f point(const Json& value) {
    if (!value.is_array() || value.size() != 2 || !value[0].is_number() || !value[1].is_number())
        throw std::runtime_error("Point must contain two finite numbers");
    const double x = value[0].get<double>(), y = value[1].get<double>();
    if (!std::isfinite(x) || !std::isfinite(y)) throw std::runtime_error("Non-finite point");
    return {static_cast<float>(x), static_cast<float>(y)};
}
void write_json(const fs::path& path, const Json& value) {
    std::ofstream file(path);
    file << value.dump(2) << '\n';
    file.flush();
    if (!file) throw std::runtime_error("Could not write geometry result");
}
}

int main(int argc, char** argv) {
    try {
        if (argc != 4) throw std::runtime_error("Usage: stage_reference REFERENCE.json FRAME.jpg NEW_OUTPUT_DIR");
        const fs::path output(argv[3]);
        if (fs::exists(output)) throw std::runtime_error("Output directory must not exist; evidence is never overwritten");
        std::ifstream input(argv[1]);
        if (!input) throw std::runtime_error("Cannot read reference JSON");
        Json spec; input >> spec;
        if (spec.at("version") != 1 || spec.at("reference_view") != "front")
            throw std::runtime_error("Version 1 front-view reference required");
        const double width = spec.at("width_mm").get<double>();
        const double height = spec.at("height_mm").get<double>();
        const auto frame = cv::imread(argv[2], cv::IMREAD_COLOR);
        if (frame.empty()) throw std::runtime_error("Cannot decode source image");
        if (frame.cols != spec.at("image_width").get<int>() || frame.rows != spec.at("image_height").get<int>())
            throw std::runtime_error("Image dimensions changed; recalibrate the camera reference");
        const auto& refs = spec.at("reference_pixels");
        if (!refs.is_array() || refs.size() != 4) throw std::runtime_error("Four perimeter references required: LL LR UR UL");
        std::array<cv::Point2f, 4> pixels;
        for (std::size_t i = 0; i < pixels.size(); ++i) pixels[i] = point(refs[i]);
        std::array<cv::Point2f, 4> mm{{{0,0},{static_cast<float>(width),0},
            {static_cast<float>(width),static_cast<float>(height)},{0,static_cast<float>(height)}}};
        if (spec.contains("reference_points_mm")) {
            const auto& physical = spec.at("reference_points_mm");
            if (!physical.is_array() || physical.size() != 4)
                throw std::runtime_error("Four physical reference coordinates required");
            for (std::size_t i = 0; i < mm.size(); ++i) mm[i] = point(physical[i]);
        }
        const std::vector<cv::Point2f> physical_polygon(mm.begin(), mm.end());
        if (!cv::isContourConvex(physical_polygon) || std::abs(cv::contourArea(physical_polygon)) < 1e-6)
            throw std::runtime_error("Physical references must form a convex quadrilateral in matching perimeter order");
        shadow::CaptureGeometry geometry;
        geometry.calibrate(pixels, mm, width, height, frame.size());
        // Bound the preview raster and preserve physical aspect ratio. Resizing
        // does not add source-camera resolution or improve metric accuracy.
        const double longest = std::max(width, height);
        const cv::Size preview_size(1 + std::max(1, static_cast<int>(std::lround(888*width/longest))),
                                    1 + std::max(1, static_cast<int>(std::lround(888*height/longest))));
        auto rectified = geometry.rectify(frame, preview_size);
        auto annotated = frame.clone();
        const char* labels[] = {"LL", "LR", "UR", "UL"};
        for (std::size_t i = 0; i < pixels.size(); ++i) {
            cv::line(annotated, pixels[i], pixels[(i+1)%4], {255,255,0}, 1);
            cv::circle(annotated, pixels[i], 3, {255,255,0}, 1);
            cv::putText(annotated, labels[i], pixels[i]+cv::Point2f(4,-4), cv::FONT_HERSHEY_SIMPLEX, .4, {255,255,0}, 1);
        }
        Json matrix = Json::array(), results = Json::array(), physical_refs = Json::array();
        for (const auto& p : mm) physical_refs.push_back({p.x,p.y});
        for (int row = 0; row < 3; ++row) matrix.push_back({geometry.matrix().at<double>(row,0),
            geometry.matrix().at<double>(row,1), geometry.matrix().at<double>(row,2)});
        std::set<std::string> names;
        if (!spec.at("points").is_array()) throw std::runtime_error("Points must be an array");
        for (const auto& item : spec.at("points")) {
            const std::string name = item.at("id").get<std::string>();
            if (name.empty() || !names.insert(name).second) throw std::runtime_error("Point IDs must be unique and nonempty");
            const auto pixel = point(item.at("pixel"));
            const auto stage = geometry.to_stage(pixel);
            const auto back = geometry.to_pixel(stage);
            const auto display = geometry.pixel_to_display(pixel, rectified.size());
            cv::circle(annotated, pixel, 3, {0,255,255}, 1);
            cv::putText(annotated, name, pixel+cv::Point2f(5,8), cv::FONT_HERSHEY_SIMPLEX, .35, {0,255,255}, 1);
            cv::circle(rectified, display, 4, {0,255,255}, 1);
            cv::putText(rectified, name, display+cv::Point2d(5,10), cv::FONT_HERSHEY_SIMPLEX, .4, {0,255,255}, 1);
            results.push_back({{"id",name},{"pixel",{pixel.x,pixel.y}},
                {"stage_mm",{stage.x,stage.y}},{"roundtrip_error_px",cv::norm(back-cv::Point2d(pixel))},
                {"interpretation",item.value("interpretation",std::string("unverified image feature"))}});
        }
        Json result{{"version",1},{"purpose","static image geometry only"},{"reference_view","front"},
            {"width_mm",width},{"height_mm",height},{"image_width",frame.cols},{"image_height",frame.rows},
            {"preview_width",rectified.cols},{"preview_height",rectified.rows},
            {"coordinate_convention","origin at curtain lower left; +x audience right; +y up; units mm"},
            {"reference_pixels",refs},{"reference_points_mm",physical_refs},
            {"pixel_to_stage",matrix},{"points",results},{"metric_accuracy_verified",false},
            {"lens_distortion_corrected",false},{"motion_calibration_ready",false},
            {"actual_servo_state",nullptr},{"reference_selection",spec.value("reference_selection",Json::object())},
            {"limitation","Numerical roundtrip is not physical accuracy. Projection is for the curtain plane, not 3D rods or joint angles."}};
        if (!fs::create_directory(output)) throw std::runtime_error("Cannot exclusively create output directory");
        if (!cv::imwrite((output/"reference_overlay.png").string(), annotated) ||
            !cv::imwrite((output/"stage_preview.png").string(), rectified))
            throw std::runtime_error("Cannot write reference previews");
        write_json(output/"geometry.json", result);
        std::cout << "IMAGE_GEOMETRY_WRITTEN_NO_MOTION_BACKEND " << output.string() << '\n';
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "ERROR " << error.what() << '\n';
        return 1;
    }
}
