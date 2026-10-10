#include "shadow/capture_geometry.hpp"
#include <opencv2/imgproc.hpp>
#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>
#include <vector>

namespace shadow {
namespace {
cv::Point2d transform(const cv::Mat& matrix, cv::Point2d p) {
    const double denominator = matrix.at<double>(2, 0)*p.x + matrix.at<double>(2, 1)*p.y + matrix.at<double>(2, 2);
    if (!std::isfinite(denominator) || std::abs(denominator) < 1e-12)
        throw std::runtime_error("Projection is singular at this point");
    cv::Point2d result((matrix.at<double>(0, 0)*p.x + matrix.at<double>(0, 1)*p.y + matrix.at<double>(0, 2))/denominator,
                       (matrix.at<double>(1, 0)*p.x + matrix.at<double>(1, 1)*p.y + matrix.at<double>(1, 2))/denominator);
    if (!std::isfinite(result.x) || !std::isfinite(result.y)) throw std::runtime_error("Projection is not finite");
    return result;
}
}
void CaptureGeometry::calibrate(const std::array<cv::Point2f, 4>& pixels,
                               const std::array<cv::Point2f, 4>& millimetres,
                               double width_mm, double height_mm, cv::Size frame_size) {
    clear();
    if (!std::isfinite(width_mm) || !std::isfinite(height_mm) || width_mm <= 0 || height_mm <= 0)
        throw std::runtime_error("Invalid stage dimensions");
    std::vector<cv::Point2f> polygon(pixels.begin(), pixels.end());
    for (auto p : pixels) if (!std::isfinite(p.x) || !std::isfinite(p.y) || p.x < 0 || p.y < 0 ||
                             p.x >= frame_size.width || p.y >= frame_size.height)
        throw std::runtime_error("Reference point is outside the image");
    if (!cv::isContourConvex(polygon) || std::abs(cv::contourArea(polygon)) < 25)
        throw std::runtime_error("Reference points must form a convex quadrilateral in perimeter order");
    // Reference coordinates use Point2f; allow only its conversion roundoff at
    // the stage's upper edges (e.g. 400.2 mm is not exactly representable).
    const double edge_x = width_mm + std::numeric_limits<float>::epsilon()*std::max(1.0, width_mm);
    const double edge_y = height_mm + std::numeric_limits<float>::epsilon()*std::max(1.0, height_mm);
    for (auto p : millimetres) if (!std::isfinite(p.x) || !std::isfinite(p.y) ||
                                  p.x < 0 || p.y < 0 || p.x > edge_x || p.y > edge_y)
        throw std::runtime_error("Reference millimetre coordinate is outside the effective stage");
    cv::Mat matrix = cv::getPerspectiveTransform(pixels.data(), millimetres.data());
    cv::Mat inverse;
    if (!cv::checkRange(matrix) || cv::invert(matrix, inverse, cv::DECOMP_LU) == 0 || !cv::checkRange(inverse))
        throw std::runtime_error("Reference points produce a singular projection");
    // Reject a projective pole crossing the reference quadrilateral.
    double sign = 0;
    for (auto p : pixels) {
        double d = matrix.at<double>(2, 0)*p.x + matrix.at<double>(2, 1)*p.y + matrix.at<double>(2, 2);
        if (std::abs(d) < 1e-12 || (sign != 0 && d*sign < 0))
            throw std::runtime_error("Reference projection crosses infinity");
        sign = d;
    }
    homography_ = matrix; inverse_ = inverse; pixels_ = pixels; frame_size_ = frame_size;
    width_ = width_mm; height_ = height_mm;
}
bool CaptureGeometry::contains_pixel(cv::Point2d pixel) const {
    if (!valid()) return false;
    std::vector<cv::Point2f> polygon(pixels_.begin(), pixels_.end());
    return pixel.x >= 0 && pixel.y >= 0 && pixel.x < frame_size_.width && pixel.y < frame_size_.height &&
           cv::pointPolygonTest(polygon, pixel, false) >= 0;
}
cv::Point2d CaptureGeometry::to_stage(cv::Point2d pixel) const {
    if (!valid() || !contains_pixel(pixel)) throw std::runtime_error("Click a point inside the reference region");
    auto p = transform(homography_, pixel);
    if (p.x < -1e-3 || p.y < -1e-3 || p.x > width_+1e-3 || p.y > height_+1e-3)
        throw std::runtime_error("Measured coordinate is outside the effective stage");
    p.x = std::max(0.0, std::min(width_, p.x)); p.y = std::max(0.0, std::min(height_, p.y));
    return p;
}
cv::Point2d CaptureGeometry::to_pixel(cv::Point2d stage) const {
    if (!valid()) throw std::runtime_error("Stage has not been calibrated");
    return transform(inverse_, stage);
}
cv::Mat CaptureGeometry::stage_to_display_matrix(cv::Size output_size) const {
    if (!valid()) throw std::runtime_error("Stage has not been calibrated");
    if (output_size.width < 2 || output_size.height < 2)
        throw std::runtime_error("Rectified image dimensions must be at least 2 pixels");
    // An inner reference polygon may be finite while extrapolation to the full
    // stage crosses a projective pole. Such a stage has no continuous preview.
    double sign = 0;
    for (auto stage : std::array<cv::Point2d, 4>{{{0, 0}, {width_, 0},
                                                 {width_, height_}, {0, height_}}}) {
        const double d = inverse_.at<double>(2, 0)*stage.x +
                         inverse_.at<double>(2, 1)*stage.y + inverse_.at<double>(2, 2);
        if (!std::isfinite(d) || std::abs(d) < 1e-12 || (sign != 0 && d*sign < 0))
            throw std::runtime_error("Stage preview projection crosses infinity");
        sign = d;
    }
    const double scale_x = (output_size.width-1)/width_;
    const double scale_y = (output_size.height-1)/height_;
    return (cv::Mat_<double>(3, 3) << scale_x, 0, 0,
            0, -scale_y, output_size.height-1, 0, 0, 1);
}
cv::Mat CaptureGeometry::rectify(const cv::Mat& frame, cv::Size output_size) const {
    const cv::Mat display = stage_to_display_matrix(output_size);
    if (frame.empty() || frame.size() != frame_size_)
        throw std::runtime_error("Source frame dimensions do not match the calibration");
    cv::Mat result;
    cv::warpPerspective(frame, result, display*homography_, output_size,
                        cv::INTER_LINEAR, cv::BORDER_CONSTANT, cv::Scalar());
    return result;
}
cv::Point2d CaptureGeometry::display_to_pixel(cv::Point2d display_point, cv::Size output_size) const {
    stage_to_display_matrix(output_size);
    if (!std::isfinite(display_point.x) || !std::isfinite(display_point.y) ||
        display_point.x < 0 || display_point.y < 0 ||
        display_point.x > output_size.width-1 || display_point.y > output_size.height-1)
        throw std::runtime_error("Click is outside the rectified stage image");
    const cv::Point2d stage(display_point.x*width_/(output_size.width-1),
                           height_ - display_point.y*height_/(output_size.height-1));
    auto pixel = to_pixel(stage);
    if (pixel.x < 0 || pixel.y < 0 || pixel.x >= frame_size_.width || pixel.y >= frame_size_.height)
        throw std::runtime_error("Rectified point is outside the source camera image");
    return pixel;
}
cv::Point2d CaptureGeometry::pixel_to_display(cv::Point2d pixel, cv::Size output_size) const {
    const cv::Mat display = stage_to_display_matrix(output_size);
    return transform(display, to_stage(pixel));
}
}
