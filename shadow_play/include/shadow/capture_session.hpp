#pragma once

#include <array>
#include <cstdint>
#include <filesystem>
#include <map>
#include <optional>
#include <string>
#include <vector>

namespace shadow {

struct CaptureAxis {
    std::string id, rod, unit;
    double min = 0, max = 0, initial = 0, jog_step = 0, max_step = 0;
};
struct CaptureAxisValue { std::string axis_id; double value = 0; std::string unit; };
struct CaptureSlide {
    std::string id, unit;
    double value = 0;
    std::string state_kind; // measured, commanded, or fixed_assumption
    std::string assumption; // required when state_kind is fixed_assumption
    // Omitted control configuration keeps a slide as recorded state only.
    bool controllable = false;
    double min = 0, max = 0, jog_step = 0, max_step = 0;
};
struct CapturePoint { std::string id, rod; std::map<std::string, double> axes; };
struct CaptureConfig {
    int version = 1;
    bool simulation_only = false;
    double stage_width_mm = 0, stage_height_mm = 0;
    std::string reference_view = "rear";
    std::array<std::array<double, 2>, 4> reference_points_mm{};
    std::vector<CaptureAxis> axes;
    std::vector<CaptureSlide> slides;
    std::vector<CapturePoint> points;
    std::string source_path, source_json;
};

CaptureConfig parse_capture_config(const std::string& json, const std::string& source_path = "");
CaptureConfig load_capture_config(const std::filesystem::path& path);
void validate_capture_config(const CaptureConfig& config);
void validate_capture_transition(const CaptureConfig& config,
                                 const std::map<std::string, double>& from,
                                 const std::map<std::string, double>& to);
bool valid_capture_rod(const std::string& rod);
std::string capture_utc_now();
std::string capture_csv_escape(const std::string& value);

struct CaptureRequest {
    std::string session_id;
    std::uint64_t seq = 0;
    std::string type = "capture_target";
    std::vector<CaptureAxisValue> axes;
    std::string json;
    std::vector<CaptureSlide> slides;
    int version = 1; // 2 when any slide is configured for control
};
struct CaptureState {
    std::vector<CaptureAxisValue> axes; // final adopted values, never filled from feedback
    std::optional<std::vector<CaptureAxisValue>> feedback; // absent remains absent
    std::vector<CaptureSlide> slides;
    std::string backend; // simulation, external, or manual_unconfirmed
    bool accepted = false, confirmed = false;
};
CaptureState parse_capture_ack(const CaptureConfig& config, const CaptureRequest& request,
                               const std::string& json);

struct CaptureSample {
    std::string sample_id, rod;
    std::uint64_t seq = 0;
    double pixel_x = 0, pixel_y = 0, stage_x_mm = 0, stage_y_mm = 0;
    int image_width = 0, image_height = 0;
    std::string frozen_at, calibration_id;
    // UTC time when the application read the frame; not sensor exposure time.
    std::optional<std::string> frame_read_at;
    // Relative path supplied by the GUI, e.g. frames/sample_0001.png.
    std::string frame_path;
    CaptureState state;
};

// Owns a newly created session directory. Existing directories are rejected.
// JSONL is authoritative; CSV is a convenience export with full state JSON.
class CaptureSession {
public:
    CaptureSession(const std::filesystem::path& directory, CaptureConfig config,
                   std::string backend);
    CaptureSession(const CaptureSession&) = delete;
    CaptureSession& operator=(const CaptureSession&) = delete;
    CaptureSession(CaptureSession&&) = default;
    CaptureSession& operator=(CaptureSession&&) = default;
    const CaptureConfig& config() const { return config_; }
    const std::filesystem::path& directory() const { return directory_; }
    const std::string& session_id() const { return session_id_; }
    const CaptureState& state() const { return state_; }
    bool synchronized() const { return synchronized_; }
    std::map<std::string, double> adopted_axes() const;
    std::map<std::string, double> adopted_slides() const;
    // capture_sync only asks the external adapter to report its current state.
    // External target requests require a valid sync; steps use adopted values.
    CaptureRequest make_request(const std::map<std::string, double>& target,
                                const std::string& type = "capture_target",
                                const std::map<std::string, double>& slide_targets = {});
    CaptureState accept_ack(const CaptureRequest& request, const std::string& json);
    void update_manual_slides(const std::vector<CaptureSlide>& slides);
    void invalidate_external(); // timeout/fault locks target requests until sync
    // PNG bytes are encoded by the GUI. Neither images nor samples are overwritten.
    void record_sample(const CaptureSample& sample, const std::vector<std::uint8_t>& png);
private:
    std::filesystem::path directory_;
    CaptureConfig config_;
    std::string backend_, session_id_;
    CaptureState state_;
    bool synchronized_ = false;
    std::uint64_t next_seq_ = 1;
    std::uint64_t adopted_seq_ = 0;
    std::optional<CaptureRequest> pending_;
    std::vector<std::string> sample_ids_;
};

} // namespace shadow
