#pragma once
#include <array>
#include <opencv2/core.hpp>

namespace shadow {
// Rear-side reference frame: origin at lower left, x right, y up, millimetres.
// Input order is lower-left, lower-right, upper-right, upper-left.
class CaptureGeometry {
public:
    void calibrate(const std::array<cv::Point2f, 4>& pixels,
                   const std::array<cv::Point2f, 4>& millimetres,
                   double width_mm, double height_mm, cv::Size frame_size);
    bool valid() const noexcept { return !homography_.empty(); }
    void clear() { homography_.release(); inverse_.release(); }
    cv::Point2d to_stage(cv::Point2d pixel) const;
    cv::Point2d to_pixel(cv::Point2d stage) const;
    bool contains_pixel(cv::Point2d pixel) const;
    // Rectify the entire physical stage, including regions beyond inner reference
    // markers. The original frame is retained by the caller for sample evidence.
    // Rectified pixels use an upper-left origin, x right, y down; stage corners
    // map to [0, output_width-1] x [0, output_height-1]. Both sizes must exceed 1.
    cv::Mat rectify(const cv::Mat& frame, cv::Size output_size) const;
    // Display coordinates are pixel-centre coordinates in the rectified image.
    // This projection may fall beyond inner markers; contains_pixel/to_stage
    // remain the authority for the permitted measurement region.
    cv::Point2d display_to_pixel(cv::Point2d display_point, cv::Size output_size) const;
    cv::Point2d pixel_to_display(cv::Point2d pixel, cv::Size output_size) const;
    const cv::Mat& matrix() const { return homography_; }
    const std::array<cv::Point2f, 4>& pixels() const { return pixels_; }
    cv::Size frame_size() const { return frame_size_; }
private:
    cv::Mat homography_, inverse_;
    std::array<cv::Point2f, 4> pixels_{};
    cv::Size frame_size_;
    double width_ = 0, height_ = 0;
    cv::Mat stage_to_display_matrix(cv::Size output_size) const;
};
}
