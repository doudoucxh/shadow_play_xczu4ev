#include "shadow/capture_session.hpp"
#include "shadow/capture_geometry.hpp"
#include "shadow/capture_http_feed.hpp"
#include <nlohmann/json.hpp>
#include <QtWidgets>
#include <opencv2/imgcodecs.hpp>
#include <opencv2/imgproc.hpp>
#include <opencv2/videoio.hpp>
#include <atomic>
#include <chrono>
#include <cmath>
#include <filesystem>
#include <functional>
#include <fstream>
#include <iostream>
#include <algorithm>
#include <iomanip>
#include <memory>
#include <mutex>
#include <optional>
#include <sstream>
#include <thread>

namespace {
using Json = nlohmann::json;
using namespace shadow;
namespace fs = std::filesystem;
long long monotonic_ms() {
    return std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count();
}
QString q(const std::string& text) { return QString::fromUtf8(text.c_str()); }
std::string s(const QString& text) { return text.toUtf8().toStdString(); }
QString rod_label(const std::string& rod) {
    if (rod == "wusong_neck") return QStringLiteral("武松身体（脖子主杆）");
    if (rod == "wusong_left") return QStringLiteral("武松左手");
    if (rod == "wusong_right") return QStringLiteral("武松右手");
    if (rod == "tiger_head") return QStringLiteral("老虎头（耳朵接点）");
    if (rod == "tiger_leg") return QStringLiteral("老虎脚（9、10 号舵机）");
    return QStringLiteral("老虎尾巴");
}
std::string padded(std::uint64_t number) {
    std::ostringstream stream; stream << std::setw(6) << std::setfill('0') << number; return stream.str();
}
void write_atomic(const fs::path& path, const std::string& text, bool refuse_existing = true) {
    if (refuse_existing && fs::exists(path)) throw std::runtime_error("Refusing to overwrite " + path.string());
    QSaveFile file(q(path.u8string()));
    if (!file.open(QIODevice::WriteOnly)) throw std::runtime_error("Cannot open " + path.string());
    const QByteArray bytes = QByteArray::fromStdString(text);
    if (file.write(bytes) != bytes.size() || !file.commit()) throw std::runtime_error("Cannot commit " + path.string());
}
struct Options {
    std::string config = "config/capture.demo.json", backend = "simulation";
    fs::path session, exchange, image, smoke, preview;
    bool demo = false;
    std::string reference_view;
    std::string frame_url, top_url;
    int camera = -1, timeout_ms = 5000;
    double width = 0, height = 0;
};
Options parse_options(int argc, char** argv) {
    Options result;
    for (int i = 1; i < argc; ++i) {
        std::string arg = argv[i];
        auto value = [&]() -> std::string {
            if (++i >= argc) throw std::runtime_error("Missing value for " + arg);
            return argv[i];
        };
        if (arg == "--config") result.config = value();
        else if (arg == "--session") result.session = fs::u8path(value());
        else if (arg == "--backend") result.backend = value();
        else if (arg == "--exchange") result.exchange = fs::u8path(value());
        else if (arg == "--camera") result.camera = std::stoi(value());
        else if (arg == "--frame-url") result.frame_url = value();
        else if (arg == "--top-url") result.top_url = value();
        else if (arg == "--image") result.image = fs::u8path(value());
        else if (arg == "--demo") result.demo = true;
        else if (arg == "--reference-view") result.reference_view = value();
        else if (arg == "--ack-timeout-ms") result.timeout_ms = std::stoi(value());
        else if (arg == "--stage-width-mm") result.width = std::stod(value());
        else if (arg == "--stage-height-mm") result.height = std::stod(value());
        else if (arg == "--smoke-test") result.smoke = fs::u8path(value());
        else if (arg == "--preview-check") result.preview = fs::u8path(value());
        else if (arg == "--help" || arg == "-h") {
            std::cout << "shadow_capture --demo|--camera N|--image FILE --config FILE --session NEW_DIR\n"
                         "  --backend simulation|manual_unconfirmed|external\n"
                         "  --exchange DIR            external driver file bridge\n"
                         "  --ack-timeout-ms N        default 5000\n"
                         "  --stage-width-mm W --stage-height-mm H\n"
                         "  --reference-view front|rear  coordinate origin is the viewed curtain bottom-left\n"
                         "  --frame-url URL           live JPEG gateway with freshness metadata\n"
                         "  --top-url URL             optional overhead monitoring gateway\n"
                         "  --preview-check FILE      verify fresh sources, save preview, then exit (no external backend)\n"
                         "See docs/capture_gui.md for Chinese instructions.\n";
            std::exit(0);
        } else throw std::runtime_error("Unknown argument: " + arg);
    }
    if (!result.reference_view.empty() && result.reference_view != "front" && result.reference_view != "rear")
        throw std::runtime_error("--reference-view must be front or rear");
    if (result.session.empty()) throw std::runtime_error("--session NEW_DIR is required");
    if (static_cast<int>(result.demo) + static_cast<int>(result.camera >= 0) + static_cast<int>(!result.image.empty()) + static_cast<int>(!result.frame_url.empty()) != 1)
        throw std::runtime_error("Select exactly one source: --demo, --camera N, --frame-url URL or --image FILE");
    if (result.backend != "simulation" && result.backend != "manual_unconfirmed" && result.backend != "external")
        throw std::runtime_error("Invalid --backend");
    if (result.backend == "external" && (result.exchange.empty() || result.demo || !result.image.empty()))
        throw std::runtime_error("External motion requires --exchange and a live --camera; demo/static images cannot control hardware");
    if (result.timeout_ms < 250 || result.timeout_ms > 60000) throw std::runtime_error("ACK timeout must be 250..60000 ms");
    if (!result.smoke.empty() && !result.demo) throw std::runtime_error("Smoke test requires --demo");
    if (!result.preview.empty() && (result.backend=="external" || !result.smoke.empty()))
        throw std::runtime_error("Preview check cannot control external hardware or combine with smoke test");
    if (!result.smoke.empty()) result.session /= "run_" + std::to_string(QDateTime::currentMSecsSinceEpoch()) + "_" + std::to_string(QCoreApplication::applicationPid());
    return result;
}

// Camera reads never block the Qt event thread. The worker owns its capture;
// a stopped detached worker may finish a blocked device read without touching UI.
class CameraFeed {
    struct Shared {
        std::mutex mutex;
        cv::Mat frame;
        std::uint64_t number = 0;
        long long read_ms = 0;
        std::string error, read_utc;
        std::uint64_t requested_epoch = 0, frame_epoch = 0;
        int discard = 0;
        std::atomic<bool> stop{false};
    };
    std::shared_ptr<Shared> shared_ = std::make_shared<Shared>();
    std::thread worker_;
public:
    explicit CameraFeed(int index) {
        auto state = shared_;
        worker_ = std::thread([state, index]() {
            try {
                cv::VideoCapture camera;
#ifdef __linux__
                camera.open(index, cv::CAP_V4L2);
#else
                camera.open(index);
#endif
                if (!camera.isOpened()) throw std::runtime_error("Camera cannot open; check USB passthrough and device number");
                camera.set(cv::CAP_PROP_BUFFERSIZE, 1); // Device support is not assumed.
                while (!state->stop.load()) {
                    cv::Mat frame;
                    if (!camera.read(frame) || frame.empty()) {
                        { std::lock_guard<std::mutex> lock(state->mutex); state->error = "Camera read failed"; }
                        std::this_thread::sleep_for(std::chrono::milliseconds(100)); continue;
                    }
                    if (frame.channels() == 1) cv::cvtColor(frame, frame, cv::COLOR_GRAY2BGR);
                    if (frame.channels() == 4) cv::cvtColor(frame, frame, cv::COLOR_BGRA2BGR);
                    if (frame.channels() != 3) throw std::runtime_error("Unsupported camera image format");
                    std::lock_guard<std::mutex> lock(state->mutex);
                    if (state->discard > 0) { --state->discard; continue; }
                    state->frame = frame.clone(); ++state->number; state->read_ms = monotonic_ms();
                    state->read_utc = capture_utc_now(); state->frame_epoch = state->requested_epoch; state->error.clear();
                }
            } catch (const std::exception& error) {
                std::lock_guard<std::mutex> lock(state->mutex); state->error = error.what();
            }
        });
    }
    ~CameraFeed() { shared_->stop.store(true); if (worker_.joinable()) worker_.detach(); }
    cv::Mat latest(std::uint64_t& number, long long& read_ms, std::uint64_t& epoch,
                   std::string& read_utc, std::string& error) {
        std::lock_guard<std::mutex> lock(shared_->mutex);
        number = shared_->number; read_ms = shared_->read_ms; error = shared_->error;
        epoch = shared_->frame_epoch; read_utc = shared_->read_utc;
        return shared_->frame.clone();
    }
    std::uint64_t discard_buffer() {
        std::lock_guard<std::mutex> lock(shared_->mutex);
        shared_->discard = 3; return ++shared_->requested_epoch;
    }
};

class FrameCanvas final : public QWidget {
    QImage image_;
    bool rectified_ = false;
    cv::Size preview_size_;
public:
    std::function<void(cv::Point2d)> clicked;
    std::function<void(const std::exception&)> rejected;
    CaptureGeometry* geometry = nullptr;
    std::vector<cv::Point2f> references;
    std::optional<cv::Point2d> measured;
    double stage_width = 800, stage_height = 500;
    bool curtain_only = true;
    explicit FrameCanvas(QWidget* parent = nullptr) : QWidget(parent) {
        setMinimumSize(500, 330); setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
    }
    void set_frame(const cv::Mat& image) {
        rectified_ = curtain_only && geometry && geometry->valid();
        cv::Mat preview = image;
        if (rectified_) {
            const double scale = std::min(1200.0/stage_width, 900.0/stage_height);
            preview_size_ = {std::max(2, static_cast<int>(std::round(stage_width*scale))),
                             std::max(2, static_cast<int>(std::round(stage_height*scale)))};
            preview = geometry->rectify(image, preview_size_);
        } else preview_size_ = image.size();
        cv::Mat rgb; cv::cvtColor(preview, rgb, cv::COLOR_BGR2RGB);
        image_ = QImage(rgb.data, rgb.cols, rgb.rows, static_cast<int>(rgb.step), QImage::Format_RGB888).copy();
        update();
    }
    QRectF image_rect() const {
        if (image_.isNull()) return {};
        QSizeF size = image_.size(); size.scale(this->size(), Qt::KeepAspectRatio);
        return QRectF((width()-size.width())/2, (height()-size.height())/2, size.width(), size.height());
    }
    QPointF display_point(cv::Point2d point) const {
        if (rectified_) point = geometry->pixel_to_display(point, preview_size_);
        auto rect = image_rect();
        const double w = rectified_ ? image_.width()-1 : image_.width();
        const double h = rectified_ ? image_.height()-1 : image_.height();
        return {rect.x()+point.x*rect.width()/w, rect.y()+point.y*rect.height()/h};
    }
    cv::Point2d source_pixel(cv::Point2d preview_pixel) const {
        return rectified_ ? geometry->display_to_pixel(preview_pixel, preview_size_) : preview_pixel;
    }
    bool rectified() const { return rectified_; }
protected:
    void paintEvent(QPaintEvent*) override {
        QPainter painter(this); painter.setRenderHint(QPainter::Antialiasing);
        painter.fillRect(rect(), QColor("#111827"));
        if (image_.isNull()) {
            painter.setPen(Qt::white); painter.drawText(rect(), Qt::AlignCenter, QStringLiteral("正在等待摄像头画面…")); return;
        }
        painter.drawImage(image_rect(), image_);
        if (geometry && geometry->valid()) {
            painter.setPen(QPen(QColor(70, 150, 140, 110), 1));
            double step = std::max(10.0, std::ceil(std::max(stage_width, stage_height)/160.0)*10.0);
            try {
                for (double x = 0; x <= stage_width; x += step)
                    painter.drawLine(display_point(geometry->to_pixel({x, 0})), display_point(geometry->to_pixel({x, stage_height})));
                for (double y = 0; y <= stage_height; y += step)
                    painter.drawLine(display_point(geometry->to_pixel({0, y})), display_point(geometry->to_pixel({stage_width, y})));
                painter.setPen(QPen(QColor("#07816f"), 2));
                auto origin = display_point(geometry->to_pixel({0, 0}));
                painter.drawText(origin+QPointF(8, -10), QStringLiteral("O (0, 0)"));
                for (double x = step*2; x < stage_width; x += step*2)
                    painter.drawText(display_point(geometry->to_pixel({x,0}))+QPointF(3,-8), QString::number(x,'f',0));
                for (double y = step*2; y < stage_height; y += step*2)
                    painter.drawText(display_point(geometry->to_pixel({0,y}))+QPointF(6,-4), QString::number(y,'f',0));
                painter.drawText(display_point(geometry->to_pixel({stage_width,0}))+QPointF(-46,-10), QStringLiteral("X / mm"));
                painter.drawText(display_point(geometry->to_pixel({0,stage_height}))+QPointF(8,20), QStringLiteral("Y / mm"));
            } catch (const std::exception&) { /* Calibration is invalidated by the owner. */ }
        }
        painter.setPen(QPen(QColor("#e05024"), 2));
        for (std::size_t i = 0; i < references.size(); ++i) {
            auto position = display_point(references[i]); painter.drawEllipse(position, 6, 6);
            painter.drawText(position+QPointF(9, -9), QString::number(static_cast<int>(i)+1));
        }
        if (measured) {
            auto position = display_point(*measured); painter.setPen(QPen(QColor("#e5423a"), 2));
            painter.drawLine(position+QPointF(-12, 0), position+QPointF(12, 0));
            painter.drawLine(position+QPointF(0, -12), position+QPointF(0, 12));
            painter.drawEllipse(position, 7, 7);
        }
    }
    void mousePressEvent(QMouseEvent* event) override {
        auto target = image_rect();
        if (event->button() != Qt::LeftButton || image_.isNull() || !target.contains(event->localPos())) return;
        const double w = rectified_ ? image_.width()-1 : image_.width();
        const double h = rectified_ ? image_.height()-1 : image_.height();
        cv::Point2d pixel((event->localPos().x()-target.x())*w/target.width(),
                          (event->localPos().y()-target.y())*h/target.height());
        try { if (clicked) clicked(source_pixel(pixel)); }
        catch (const std::exception& error) { if (rejected) rejected(error); }
    }
};

class CaptureWindow final : public QMainWindow {
    enum class Phase { Unready, Ready, Pending, FreshFrame, Frozen, References, Fault };
    Options options_;
    CaptureSession session_;
    CaptureGeometry geometry_;
    std::unique_ptr<CameraFeed> camera_;
    std::unique_ptr<HttpFrameFeed> http_camera_, top_camera_;
    QLabel *top_preview_ = nullptr, *top_note_ = nullptr;
    cv::Mat latest_, frozen_, reference_frame_;
    std::uint64_t frame_number_ = 0, freeze_after_frame_ = 0, state_seq_ = 0, frozen_seq_ = 0,
                  frame_epoch_ = 0, freeze_epoch_ = 0;
    long long frame_read_ms_ = 0, freeze_started_ms_ = 0, request_started_ms_ = 0;
    Phase phase_ = Phase::Unready;
    CaptureState frozen_state_;
    std::string frozen_at_, frozen_rod_, calibration_id_, frame_read_at_, frozen_read_at_;
    std::optional<CaptureRequest> pending_;
    std::optional<cv::Point2d> measurement_;
    fs::path exchange_dir_;
    bool freeze_after_sync_ = false, paused_ = false, plan_applied_ = false, source_fault_ = false, editor_dirty_ = false;
    std::size_t plan_index_ = 0, saved_count_ = 0, calibration_count_ = 0;
    FrameCanvas* canvas_ = nullptr;
    QLabel *status_ = nullptr, *coordinate_ = nullptr, *plan_label_ = nullptr, *axis_note_ = nullptr, *source_note_ = nullptr,
           *adopted_note_ = nullptr;
    QComboBox* rod_ = nullptr;
    QCheckBox *settled_ = nullptr, *auto_next_ = nullptr, *confirmed_sample_ = nullptr, *curtain_only_ = nullptr;
    QPushButton *sync_ = nullptr, *apply_ = nullptr, *execute_ = nullptr, *freeze_ = nullptr,
                *save_ = nullptr, *cancel_ = nullptr, *calibrate_ = nullptr, *skip_ = nullptr, *pause_ = nullptr;
    std::vector<QDoubleSpinBox*> axis_spins_, slide_spins_;
    std::vector<QWidget*> axis_rows_;
    QFormLayout* axis_form_ = nullptr;
    QCheckBox* show_all_axes_ = nullptr;
    std::vector<QPushButton*> jog_buttons_;
    std::vector<QPushButton*> slide_jog_buttons_;
    QTableWidget *records_ = nullptr;
    QTimer timer_;
    QString detail_;
    bool smoke_ = false;

    std::string selected_rod() const { return s(rod_->currentData().toString()); }
    bool movement_available() const {
        return phase_ == Phase::Ready && !paused_ && !plan_applied_ && !source_fault_ &&
               (options_.backend != "external" || session_.synchronized());
    }
    void message(const QString& text) { detail_ = text; update_controls(); }
    void fail(const std::exception& error) {
        message(QStringLiteral("操作未完成：") + q(error.what()));
        if (smoke_) throw;
        QMessageBox::warning(this, QStringLiteral("请检查"), q(error.what()));
    }
    template<class Function> void guarded(Function action) {
        try { action(); } catch (const std::exception& error) { fail(error); }
    }
    QPushButton* button(QLayout* layout, const QString& text, std::function<void()> action) {
        auto* result = new QPushButton(text); layout->addWidget(result);
        connect(result, &QPushButton::clicked, this, [this, action]() { guarded(action); }); return result;
    }
    void update_controls() {
        const bool ready = phase_ == Phase::Ready;
        sync_->setEnabled((ready || phase_ == Phase::Unready || phase_ == Phase::Fault) && !source_fault_);
        apply_->setEnabled(movement_available()); execute_->setEnabled(movement_available() && plan_index_ < session_.config().points.size());
        for (auto* button : jog_buttons_) button->setEnabled(movement_available());
        for (auto* button : slide_jog_buttons_) button->setEnabled(movement_available());
        const bool editable = ready && !plan_applied_ && !paused_;
        for (auto* spin : axis_spins_) spin->setEnabled(editable);
        for (std::size_t i=0; i<slide_spins_.size(); ++i)
            slide_spins_[i]->setEnabled(editable && (session_.config().slides[i].controllable || options_.backend == "manual_unconfirmed"));
        rod_->setEnabled(ready && !plan_applied_);
        for (std::size_t i = 0; i < axis_rows_.size(); ++i) {
            const bool show = show_all_axes_->isChecked() || session_.config().axes[i].rod == selected_rod();
            axis_rows_[i]->setVisible(show); axis_form_->labelForField(axis_rows_[i])->setVisible(show);
        }
        settled_->setEnabled(ready && !source_fault_);
        freeze_->setEnabled(ready && !editor_dirty_ && settled_->isChecked() && geometry_.valid() && !latest_.empty() && !source_fault_);
        confirmed_sample_->setEnabled(phase_ == Phase::Frozen && measurement_.has_value() && !source_fault_);
        save_->setEnabled(phase_ == Phase::Frozen && measurement_.has_value() && confirmed_sample_->isChecked() && !source_fault_);
        cancel_->setEnabled(phase_ == Phase::Frozen || phase_ == Phase::FreshFrame || phase_ == Phase::References);
        calibrate_->setEnabled((ready || phase_ == Phase::Unready || phase_ == Phase::Fault) && !latest_.empty() && !source_fault_);
        skip_->setEnabled(ready && plan_applied_ && !paused_);
        pause_->setText(paused_ ? QStringLiteral("恢复发令") : QStringLiteral("暂停发令"));
        QString phase;
        switch (phase_) {
            case Phase::Unready: phase = QStringLiteral("请读取 / 登记当前状态"); break;
            case Phase::Ready: phase = QStringLiteral("等待人工确认停稳"); break;
            case Phase::Pending: phase = QStringLiteral("等待驱动确认；禁止新指令"); break;
            case Phase::FreshFrame: phase = QStringLiteral("获取停稳后的新画面…"); break;
            case Phase::Frozen: phase = QStringLiteral("画面已冻结；请点击实际连接点"); break;
            case Phase::References: phase = QStringLiteral("正在设置幕面四个参考点"); break;
            case Phase::Fault: phase = QStringLiteral("状态失效；请重新读取驱动状态"); break;
        }
        status_->setText((paused_ ? QStringLiteral("【已暂停后续发令】 ") : QString()) + phase + QStringLiteral("\n") + detail_);
        const auto& points = session_.config().points;
        plan_label_->setText(plan_index_ < points.size()
            ? QStringLiteral("采样列表 %1 / %2 · %3\n本组：%4").arg(plan_index_+1).arg(points.size())
                .arg(rod_label(points[plan_index_].rod)).arg(q(points[plan_index_].id))
            : QStringLiteral("采样列表已完成。已保存 %1 条记录。可继续手动采集。").arg(saved_count_));
        update_adopted_preview();
    }
    void update_adopted_preview() {
        const bool frozen = phase_ == Phase::Frozen;
        const auto& state = frozen ? frozen_state_ : session_.state();
        const auto rod = frozen ? frozen_rod_ : selected_rod();
        const auto seq = frozen ? frozen_seq_ : state_seq_;
        QString text = QStringLiteral("%1 · 状态 %2\n").arg(rod_label(rod)).arg(seq);
        for (const auto& axis : session_.config().axes) if (axis.rod==rod) {
            const auto value = std::find_if(state.axes.begin(),state.axes.end(),[&](const CaptureAxisValue& v) { return v.axis_id==axis.id; });
            if (value==state.axes.end()) continue;
            const QString unit = axis.unit=="us" ? QStringLiteral("μs（PWM 脉宽）") : q(axis.unit);
            text += QStringLiteral("%1 = %2 %3\n").arg(q(axis.id)).arg(value->value,0,'f',3).arg(unit);
        }
        for (const auto& slide : state.slides)
            text += QStringLiteral("%1 = %2 %3\n").arg(q(slide.id)).arg(slide.value,0,'f',3).arg(q(slide.unit));
        text += options_.backend=="external" ? (session_.synchronized()?QStringLiteral("驱动确认采用值；实物停稳需观察。") : QStringLiteral("尚未读取驱动状态。"))
            : options_.backend=="simulation" ? QStringLiteral("demo 模拟值，不产生 PWM。") : QStringLiteral("人工登记值，未由驱动确认。");
        if (frozen) text += QStringLiteral(" 画面已绑定。");
        adopted_note_->setText(text);
    }
    void copy_state_to_widgets() {
        auto values = session_.adopted_axes();
        for (std::size_t i = 0; i < axis_spins_.size(); ++i) {
            QSignalBlocker blocker(axis_spins_[i]); axis_spins_[i]->setValue(values.at(session_.config().axes[i].id));
        }
        for (std::size_t i = 0; i < slide_spins_.size(); ++i) {
            const auto& id = session_.config().slides[i].id;
            const auto found = std::find_if(session_.state().slides.begin(), session_.state().slides.end(),
                [&](const CaptureSlide& slide) { return slide.id == id; });
            if (found == session_.state().slides.end()) throw std::runtime_error("Missing slide state: " + id);
            QSignalBlocker blocker(slide_spins_[i]); slide_spins_[i]->setValue(found->value);
        }
        editor_dirty_ = false;
        axis_note_->setText(options_.backend == "external" ? QStringLiteral("显示驱动最终采用值；真实位置反馈单独保存在记录中。")
            : options_.backend == "manual_unconfirmed" ? QStringLiteral("人工登记值，未由驱动确认。请从实际控制工具如实抄入。")
            : QStringLiteral("模拟单位 demo，不产生 PWM。"));
    }
    std::map<std::string, double> editor_values() const {
        std::map<std::string, double> values;
        for (std::size_t i = 0; i < axis_spins_.size(); ++i) values[session_.config().axes[i].id] = axis_spins_[i]->value();
        return values;
    }
    void register_manual_slides() {
        if (options_.backend != "manual_unconfirmed") return;
        auto slides = session_.state().slides;
        for (std::size_t i = 0; i < slides.size(); ++i) {
            const auto found = std::find_if(slides.begin(), slides.end(), [&](const CaptureSlide& slide) {
                return slide.id == session_.config().slides[i].id;
            });
            if (found == slides.end()) throw std::runtime_error("Missing manual slide");
            if (session_.config().slides[i].controllable) continue;
            found->value = slide_spins_[i]->value(); found->state_kind = "fixed_assumption";
            found->assumption = "人工录入，未提供位置反馈";
        }
        session_.update_manual_slides(slides);
    }
    void request(const std::map<std::string, double>& values, bool sync, bool freeze_after = false,
                 const std::map<std::string,double>& slides = {}) {
        register_manual_slides();
        auto next = session_.make_request(values, sync ? "capture_sync" : "capture_target", slides);
        settled_->setChecked(false); measurement_.reset(); canvas_->measured.reset(); frozen_.release();
        confirmed_sample_->setChecked(false); coordinate_->setText(QStringLiteral("等待冻结画面并点击连接点。"));
        freeze_after_sync_ = freeze_after;
        if (options_.backend == "external") {
            pending_ = next; request_started_ms_ = monotonic_ms(); phase_ = Phase::Pending;
            fs::path file = exchange_dir_/"requests"/("request_" + padded(next.seq) + ".json");
            try { write_atomic(file, next.json + "\n"); }
            catch (...) { pending_.reset(); session_.invalidate_external(); phase_ = Phase::Fault; throw; }
            message(QStringLiteral("请求 %1 已写入，等待同会话、同序号的 ACK。").arg(next.seq));
        } else {
            state_seq_ = next.seq; phase_ = Phase::Ready; copy_state_to_widgets();
            message(QStringLiteral("状态编号 %1。请观察停稳后勾选确认。").arg(state_seq_));
        }
    }
    void sync_state() {
        if (phase_ == Phase::Pending || phase_ == Phase::Frozen || phase_ == Phase::References) return;
        plan_applied_ = false; request(editor_values(), options_.backend == "external", false,
            options_.backend=="external" ? std::map<std::string,double>{} : slide_editor_values());
    }
    std::map<std::string,double> slide_editor_values() const {
        std::map<std::string,double> values;
        for (std::size_t i=0; i<slide_spins_.size(); ++i) if (session_.config().slides[i].controllable)
            values[session_.config().slides[i].id] = slide_spins_[i]->value();
        return values;
    }
    void apply_editors() { if (movement_available()) request(editor_values(), false, false, slide_editor_values()); }
    void jog(std::size_t index, double direction) {
        if (!movement_available()) return;
        auto target = session_.adopted_axes(); const auto& axis = session_.config().axes[index];
        target.at(axis.id) += direction*axis.jog_step; request(target, false);
    }
    void jog_slide(std::size_t index, double direction) {
        if (!movement_available()) return;
        const auto& slide = session_.config().slides[index];
        if (!slide.controllable) return;
        const double value = session_.adopted_slides().at(slide.id) + direction*slide.jog_step;
        request(session_.adopted_axes(), false, false, {{slide.id,value}});
    }
    void execute_plan() {
        if (!movement_available() || plan_index_ >= session_.config().points.size()) return;
        const auto& point = session_.config().points[plan_index_];
        rod_->setCurrentIndex(rod_->findData(q(point.rod)));
        request(point.axes, false); plan_applied_ = true; update_controls();
    }
    void skip_point() {
        if (phase_ != Phase::Ready || !plan_applied_) return;
        Json event{{"type", "skipped"}, {"session_id", session_.session_id()}, {"seq", state_seq_},
                   {"point_id", session_.config().points[plan_index_].id}, {"time", capture_utc_now()}};
        std::ofstream log(session_.directory()/"skipped.jsonl", std::ios::app);
        log << event.dump() << '\n'; if (!log) throw std::runtime_error("Cannot write skipped point log");
        plan_applied_ = false; ++plan_index_; settled_->setChecked(false); message(QStringLiteral("已跳过本组。下一组需点击执行。"));
    }
    void poll_ack() {
        if (!pending_) return;
        if (monotonic_ms()-request_started_ms_ > options_.timeout_ms) {
            pending_.reset(); session_.invalidate_external(); phase_ = Phase::Fault; plan_applied_ = false;
            freeze_after_sync_ = false; message(QStringLiteral("驱动确认超时；迟到 ACK 不会配入样本。需要重新读取状态。"));
            return;
        }
        auto path = exchange_dir_/"acks"/("ack_" + padded(pending_->seq) + ".json");
        if (fs::exists(path)) {
            try {
                if (fs::file_size(path) > 1024*1024) throw std::runtime_error("ACK file exceeds 1 MiB");
                std::ifstream file(path); std::string text((std::istreambuf_iterator<char>(file)), {});
                auto before = session_.adopted_axes(); const auto slides_before = session_.state().slides;
                auto ack = session_.accept_ack(*pending_, text);
                (void)ack; state_seq_ = pending_->seq; pending_.reset(); phase_ = Phase::Ready; copy_state_to_widgets();
                bool slides_equal = slides_before.size() == session_.state().slides.size();
                for (const auto& previous : slides_before) {
                    const auto found = std::find_if(session_.state().slides.begin(),session_.state().slides.end(),
                        [&](const CaptureSlide& slide) { return slide.id == previous.id; });
                    slides_equal = slides_equal && found != session_.state().slides.end();
                    if (found != session_.state().slides.end()) slides_equal = slides_equal && found->value == previous.value &&
                        found->unit == previous.unit && found->state_kind == previous.state_kind && found->assumption == previous.assumption;
                }
                if (freeze_after_sync_ && before == session_.adopted_axes() && slides_equal) {
                    freeze_after_sync_ = false; begin_fresh_frame();
                } else {
                    freeze_after_sync_ = false; settled_->setChecked(false);
                    message(QStringLiteral("驱动已确认状态 %1。请重新观察停稳。").arg(state_seq_));
                }
            } catch (const std::exception& error) {
                pending_.reset(); session_.invalidate_external(); phase_ = Phase::Fault; freeze_after_sync_ = false;
                plan_applied_ = false; message(QStringLiteral("ACK 无效：") + q(error.what()) + QStringLiteral("。请核对后重新读取状态。"));
            }
        }
    }
    cv::Point2d demo_point(const std::string& rod) const {
        cv::Point2d base;
        if (rod == "wusong_neck") base = {590, 230};
        else if (rod == "wusong_left") base = {500, 280};
        else if (rod == "wusong_right") base = {700, 290};
        else if (rod == "tiger_head") base = {420, 395};
        else if (rod == "tiger_leg") base = {340, 475};
        else base = {190, 355};
        int axis = 0; auto values = session_.adopted_axes();
        for (const auto& configured : session_.config().axes) if (configured.rod == rod) {
            if (axis++ == 0) base.x += values.at(configured.id)*55; else base.y -= values.at(configured.id)*45;
        }
        const bool wusong = rod.rfind("wusong_",0)==0;
        const auto id = wusong ? "wusong_slide" : "tiger_slide";
        for (const auto& slide : session_.state().slides) if (slide.id==id) base.x += slide.value*60;
        return base;
    }
    cv::Mat demo_frame() const {
        cv::Mat image(600, 960, CV_8UC3, cv::Scalar(235, 232, 222));
        cv::rectangle(image, {80, 50}, {880, 550}, cv::Scalar(252, 250, 244), cv::FILLED);
        cv::rectangle(image, {80, 50}, {880, 550}, cv::Scalar(145, 139, 128), 3);
        auto neck = demo_point("wusong_neck"), left = demo_point("wusong_left"), right = demo_point("wusong_right");
        cv::Scalar green(99, 139, 63), dark(51, 67, 48), tiger(56, 152, 222);
        cv::circle(image, {static_cast<int>(neck.x), static_cast<int>(neck.y-45)}, 30, green, cv::FILLED);
        std::vector<cv::Point> body{{static_cast<int>(neck.x-24),static_cast<int>(neck.y)},
            {static_cast<int>(neck.x+24),static_cast<int>(neck.y)}, {static_cast<int>(neck.x+38),420}, {static_cast<int>(neck.x-38),420}};
        cv::fillConvexPoly(image, body, green);
        cv::line(image, neck, left, dark, 10); cv::line(image, neck, right, dark, 10);
        cv::line(image, {static_cast<int>(neck.x-16), 417}, {static_cast<int>(neck.x-28), 492}, dark, 13);
        cv::line(image, {static_cast<int>(neck.x+16), 417}, {static_cast<int>(neck.x+31), 492}, dark, 13);
        auto head = demo_point("tiger_head"), tail = demo_point("tiger_tail");
        cv::ellipse(image, {310, 426}, {83, 35}, 0, 0, 360, tiger, cv::FILLED);
        cv::circle(image, head, 30, tiger, cv::FILLED); cv::line(image, {232, 417}, tail, tiger, 13);
        for (int x : {260, 300, 340, 365}) {
            cv::line(image, {x, 441}, {x-8, 492}, dark, 9); cv::line(image, {x, 405}, {x+12, 440}, dark, 5);
        }
        std::vector<std::string> rods;
        for (const auto& axis : session_.config().axes)
            if (std::find(rods.begin(),rods.end(),axis.rod)==rods.end()) rods.push_back(axis.rod);
        for (std::size_t i = 0; i < rods.size(); ++i) {
            auto point = demo_point(rods[i]); cv::line(image, {150+static_cast<int>(i)*145, 545}, point, cv::Scalar(143, 185, 207), 2);
            cv::circle(image, point, 8, selected_rod() == rods[i] ? cv::Scalar(70, 80, 224) : cv::Scalar(128, 54, 30), cv::FILLED);
        }
        return image;
    }
    void refresh_frame() {
        source_fault_ = false;
        if (options_.demo) { latest_ = demo_frame(); ++frame_number_; frame_read_ms_ = monotonic_ms(); frame_read_at_ = capture_utc_now(); }
        else if (camera_) {
            std::string error; auto next = camera_->latest(frame_number_, frame_read_ms_, frame_epoch_, frame_read_at_, error);
            source_fault_ = !error.empty() || next.empty() || !frame_read_ms_ || monotonic_ms()-frame_read_ms_ > 2000;
            if (source_fault_) source_note_->setText(QStringLiteral("相机画面异常 / 过期：")+q(error));
            else source_note_->setText(QStringLiteral("实时相机 · %1 × %2 · 读取编号 %3").arg(next.cols).arg(next.rows).arg(frame_number_));
            if (!next.empty()) latest_ = next;
        }
        else if (http_camera_) {
            std::string error;
            auto next = http_camera_->latest(frame_number_, frame_read_ms_, frame_epoch_, frame_read_at_, error);
            source_fault_ = !error.empty() || next.empty() || !frame_read_ms_ || monotonic_ms()-frame_read_ms_ > 1500;
            source_note_->setText(source_fault_ ? QStringLiteral("正面取景异常 / 过期：")+q(error)
                : QStringLiteral("Sony / 网络实时取景 · %1 × %2 · 新帧 %3").arg(next.cols).arg(next.rows).arg(frame_number_));
            if (!next.empty()) latest_ = next;
        }
        if (top_camera_) {
            std::uint64_t number=0, epoch=0; long long read=0; std::string utc, error;
            auto top=top_camera_->latest(number,read,epoch,utc,error);
            const bool bad=!error.empty() || top.empty() || !read || monotonic_ms()-read>1500;
            source_fault_ = source_fault_ || bad;
            top_note_->setText(bad ? QStringLiteral("顶视图异常，点动与采样已锁定：")+q(error)
                : QStringLiteral("Camo 顶视监看 · 新帧 %1\n只观察机构；正面与顶视未经硬件同步。幕布坐标只取正面图。").arg(number));
            if (!bad) {
                cv::Mat rgb; cv::cvtColor(top,rgb,cv::COLOR_BGR2RGB);
                QImage image(rgb.data,rgb.cols,rgb.rows,static_cast<int>(rgb.step),QImage::Format_RGB888);
                top_preview_->setPixmap(QPixmap::fromImage(image).scaled(top_preview_->size(),Qt::KeepAspectRatio,Qt::SmoothTransformation));
            } else { top_preview_->clear(); top_preview_->setText(QStringLiteral("顶视图不可用")); }
        }
        if (latest_.empty()) { update_controls(); return; }
        if (phase_ == Phase::References && latest_.size() != reference_frame_.size()) {
            cancel_capture(); message(QStringLiteral("参考点设置期间相机尺寸改变，请重新设置。"));
        }
        if (geometry_.valid() && latest_.size() != geometry_.frame_size()) {
            geometry_.clear(); calibration_id_.clear(); cancel_capture();
            message(QStringLiteral("相机分辨率改变，幕面转换已失效，请重新设置参考点。"));
        }
        if (source_fault_ && (phase_ == Phase::Frozen || phase_ == Phase::FreshFrame)) {
            cancel_capture(); message(QStringLiteral("相机失联或画面过期，本次取点已取消。"));
        }
        if (phase_ == Phase::FreshFrame && frame_number_ > freeze_after_frame_ && frame_read_ms_ >= freeze_started_ms_ &&
            (!(camera_ || http_camera_) || frame_epoch_ >= freeze_epoch_) && !source_fault_) {
            frozen_ = latest_.clone(); frozen_state_ = session_.state(); frozen_at_ = capture_utc_now();
            frozen_seq_ = state_seq_; frozen_read_at_ = frame_read_at_; frozen_rod_ = selected_rod(); phase_ = Phase::Frozen;
            message(QStringLiteral("画面与状态 %1 已锁定。点击实际连接点后保存。").arg(state_seq_));
        } else if (phase_ == Phase::FreshFrame && monotonic_ms()-freeze_started_ms_ > 5000) {
            cancel_capture(); message(QStringLiteral("没有取得新的相机画面，请检查相机后重试。"));
        }
        canvas_->curtain_only = curtain_only_->isChecked() && phase_ != Phase::References;
        if (phase_ == Phase::Frozen) canvas_->set_frame(frozen_);
        else if (phase_ == Phase::References) canvas_->set_frame(reference_frame_);
        else canvas_->set_frame(latest_);
        update_controls();
    }
    void begin_fresh_frame() {
        measurement_.reset(); canvas_->measured.reset(); freeze_started_ms_ = monotonic_ms();
        confirmed_sample_->setChecked(false);
        freeze_after_frame_ = frame_number_; phase_ = Phase::FreshFrame;
        if (camera_) freeze_epoch_ = camera_->discard_buffer();
        if (http_camera_) freeze_epoch_ = http_camera_->discard_buffer();
        // A static image is explicitly marked offline; no camera freshness claim.
        if (!options_.image.empty()) {
            frozen_ = latest_.clone(); frozen_state_ = session_.state(); frozen_at_ = capture_utc_now();
            frozen_seq_ = state_seq_; frozen_read_at_ = frame_read_at_; frozen_rod_ = selected_rod(); phase_ = Phase::Frozen;
        }
        message(QStringLiteral("正在获取新画面。采样期间保持机构不动。"));
    }
    void freeze_frame() {
        if (phase_ != Phase::Ready || editor_dirty_ || !settled_->isChecked() || !geometry_.valid() || source_fault_) return;
        if (options_.backend == "external") {
            // Read back the current submitted state immediately before freezing.
            request(session_.adopted_axes(), true, true);
        } else begin_fresh_frame();
    }
    void cancel_capture() {
        measurement_.reset(); canvas_->measured.reset(); frozen_.release(); reference_frame_.release();
        confirmed_sample_->setChecked(false); coordinate_->setText(QStringLiteral("等待冻结画面并点击连接点。"));
        canvas_->references.clear();
        if (!pending_) phase_ = session_.synchronized() || options_.backend != "external" ? Phase::Ready : Phase::Unready;
        settled_->setChecked(false); message(QStringLiteral("取点已取消，可重新观察停稳或设置参考点。"));
    }
    void start_calibration() {
        if (latest_.empty() || phase_ == Phase::Pending || phase_ == Phase::Frozen) return;
        reference_frame_ = latest_.clone(); canvas_->references.clear(); geometry_.clear(); calibration_id_.clear();
        phase_ = Phase::References; settled_->setChecked(false);
        canvas_->curtain_only = false; canvas_->set_frame(reference_frame_);
        message(QStringLiteral("按配置参考点依次点击：1 左下、2 右下、3 右上、4 左上。"));
    }
    void save_geometry(const std::array<cv::Point2f, 4>& pixels) {
        std::array<cv::Point2f, 4> mm;
        for (std::size_t i = 0; i < mm.size(); ++i) mm[i] = {
            static_cast<float>(session_.config().reference_points_mm[i][0]), static_cast<float>(session_.config().reference_points_mm[i][1])};
        geometry_.calibrate(pixels, mm, session_.config().stage_width_mm, session_.config().stage_height_mm, reference_frame_.size());
        try { geometry_.rectify(reference_frame_,{800,500}); }
        catch (...) { geometry_.clear(); throw; }
        calibration_id_ = "calibration_" + padded(++calibration_count_);
        Json matrix = Json::array();
        for (int row = 0; row < 3; ++row) matrix.push_back({geometry_.matrix().at<double>(row,0), geometry_.matrix().at<double>(row,1), geometry_.matrix().at<double>(row,2)});
        Json pixel_json = Json::array(); for (auto p : pixels) pixel_json.push_back({p.x,p.y});
        Json calibration{{"version",1},{"calibration_id",calibration_id_},{"reference_view",session_.config().reference_view},
            {"width_mm",session_.config().stage_width_mm},{"height_mm",session_.config().stage_height_mm},
            {"image_width",latest_.cols},{"image_height",latest_.rows},{"reference_pixels",pixel_json},
            {"reference_points_mm",session_.config().reference_points_mm},{"pixel_to_stage",matrix},
            {"created_at",capture_utc_now()},{"lens_distortion_corrected",false}};
        write_atomic(session_.directory()/(calibration_id_+".json"), calibration.dump(2)+"\n");
        canvas_->references.clear(); reference_frame_.release(); phase_ = Phase::Ready;
        message(QStringLiteral("幕面转换已保存。先用已知内部点检查误差，再开始采集。"));
    }
    void on_pixel(cv::Point2d point) {
        if (phase_ == Phase::References) {
            canvas_->references.emplace_back(static_cast<float>(point.x),static_cast<float>(point.y));
            if (canvas_->references.size() == 4) {
                std::array<cv::Point2f,4> pixels;
                std::copy(canvas_->references.begin(), canvas_->references.end(), pixels.begin());
                try { save_geometry(pixels); } catch (...) { canvas_->references.clear(); throw; }
            } else message(QStringLiteral("已选 %1 / 4 个参考点，请继续。 ").arg(canvas_->references.size()));
        } else if (phase_ == Phase::Frozen) {
            auto mm = geometry_.to_stage(point); measurement_ = point; canvas_->measured = point;
            confirmed_sample_->setChecked(false);
            coordinate_->setText(QStringLiteral("X = %1 mm     Y = %2 mm\n原始相机像素 (%3, %4)")
                .arg(mm.x,0,'f',2).arg(mm.y,0,'f',2).arg(point.x,0,'f',1).arg(point.y,0,'f',1));
            message(QStringLiteral("取点完成。保存时将锁定状态 %1 与当前照片配对。").arg(state_seq_));
        } else if (geometry_.valid()) {
            auto mm = geometry_.to_stage(point);
            coordinate_->setText(QStringLiteral("检查点：(%1, %2) mm\n仅检查坐标；冻结后才能保存样本。").arg(mm.x,0,'f',2).arg(mm.y,0,'f',2));
        }
        canvas_->update(); update_controls();
    }
    void save_sample() {
        if (phase_ != Phase::Frozen || !measurement_ || !confirmed_sample_->isChecked() || source_fault_) return;
        auto mm = geometry_.to_stage(*measurement_);
        CaptureSample sample;
        sample.sample_id = "sample_"+padded(saved_count_+1); sample.rod = frozen_rod_; sample.seq = frozen_seq_;
        sample.pixel_x = measurement_->x; sample.pixel_y = measurement_->y; sample.stage_x_mm = mm.x; sample.stage_y_mm = mm.y;
        sample.image_width = frozen_.cols; sample.image_height = frozen_.rows; sample.frozen_at = frozen_at_;
        sample.frame_read_at = frozen_read_at_;
        sample.calibration_id = calibration_id_; sample.frame_path = "frames/"+sample.sample_id+".png"; sample.state = frozen_state_;
        std::vector<std::uint8_t> png;
        if (!cv::imencode(".png", frozen_, png)) throw std::runtime_error("PNG encoding failed");
        session_.record_sample(sample, png); ++saved_count_;
        int row = records_->rowCount(); records_->insertRow(row);
        const QStringList columns{q(sample.sample_id),rod_label(sample.rod),QString::number(mm.x,'f',2),
            QString::number(mm.y,'f',2),QString::number(sample.seq),q(sample.state.backend)};
        for (int column = 0; column < columns.size(); ++column) records_->setItem(row,column,new QTableWidgetItem(columns[column]));
        records_->scrollToBottom();
        const bool advance = plan_applied_;
        if (advance) { ++plan_index_; plan_applied_ = false; }
        cancel_capture(); message(QStringLiteral("已保存 %1。照片、JSONL 和 CSV 在本次会话目录。").arg(q(sample.sample_id)));
        if (advance && auto_next_->isChecked() && !paused_ && plan_index_ < session_.config().points.size()) execute_plan();
    }
    void build_ui() {
        setWindowTitle(QStringLiteral("皮影舵机定位采集 · Shadow Capture")); resize(1400,980);
        auto* root = new QWidget; auto* layout = new QVBoxLayout(root); layout->setContentsMargins(18,16,18,16); setCentralWidget(root);
        auto* title = new QLabel(QStringLiteral("皮影动作标定采集")); QFont heading = title->font(); heading.setPointSize(20); heading.setBold(true); title->setFont(heading); layout->addWidget(title);
        auto* backend = new QLabel(options_.backend == "simulation" ? QStringLiteral("模拟模式 · 合成指令，不连接真实电机")
            : options_.backend == "manual_unconfirmed" ? QStringLiteral("手工登记模式 · 从实际点动工具抄入命令；本模式不发电机命令")
            : QStringLiteral("外部驱动模式 · 通过适配器连接电机驱动；先读取现态，再发目标"));
        backend->setStyleSheet("color:#946012;font-weight:600;"); layout->addWidget(backend);
        auto* session_label = new QLabel(QStringLiteral("会话：%1\n保存目录：%2").arg(q(session_.session_id())).arg(q(session_.directory().u8string())));
        session_label->setTextInteractionFlags(Qt::TextSelectableByMouse); session_label->setWordWrap(true); layout->addWidget(session_label);
        auto* body = new QHBoxLayout; layout->addLayout(body,1);
        auto* left = new QVBoxLayout; body->addLayout(left,1);
        source_note_ = new QLabel(options_.demo ? QStringLiteral("合成幕面 · 仅用于验证软件操作；红色点为当前选择的连接点")
                                               : !options_.image.empty() ? QStringLiteral("离线照片 · 不表示当前实物姿态") : QStringLiteral("正在打开相机…"));
        source_note_->setWordWrap(true); left->addWidget(source_note_);
        curtain_only_=new QCheckBox(QStringLiteral("仅显示有效幕布（设置四点后自动透视校正）"));
        curtain_only_->setChecked(true); left->addWidget(curtain_only_);
        connect(curtain_only_,&QCheckBox::toggled,this,[this](bool enabled) { canvas_->curtain_only=enabled; refresh_frame(); });
        canvas_ = new FrameCanvas; canvas_->geometry = &geometry_; canvas_->stage_width=session_.config().stage_width_mm; canvas_->stage_height=session_.config().stage_height_mm;
        canvas_->rejected = [this](const std::exception& error) { fail(error); };
        canvas_->clicked = [this](cv::Point2d point) { guarded([&]() { on_pixel(point); }); }; left->addWidget(canvas_,1);
        auto* stage = new QLabel(QStringLiteral("%1 · 左下角原点 · X 向右 / Y 向上 · 有效幕面 %2 × %3 mm")
            .arg(session_.config().reference_view == "front" ? QStringLiteral("观众视角") : QStringLiteral("幕后视角"))
            .arg(session_.config().stage_width_mm).arg(session_.config().stage_height_mm)); stage->setWordWrap(true); left->addWidget(stage);
        records_ = new QTableWidget(0,6); records_->setHorizontalHeaderLabels({QStringLiteral("样本编号"),QStringLiteral("连接点"),"X / mm","Y / mm",QStringLiteral("状态编号"),QStringLiteral("来源")});
        records_->setEditTriggers(QAbstractItemView::NoEditTriggers); records_->horizontalHeader()->setSectionResizeMode(QHeaderView::Stretch); records_->setMaximumHeight(180); left->addWidget(records_);
        if (!options_.top_url.empty()) {
            auto* top_row = new QHBoxLayout; left->addLayout(top_row);
            top_preview_ = new QLabel; top_preview_->setFixedSize(300,170); top_preview_->setAlignment(Qt::AlignCenter);
            top_preview_->setStyleSheet("background:#172429;color:white"); top_row->addWidget(top_preview_);
            top_note_ = new QLabel(QStringLiteral("顶视图连接中；只用于观察机构，不参与幕布坐标换算。"));
            top_note_->setWordWrap(true); top_row->addWidget(top_note_,1);
        }
        auto* side_content = new QWidget; auto* side = new QVBoxLayout(side_content);
        auto* right = new QVBoxLayout; body->addLayout(right);
        auto* scroll = new QScrollArea; scroll->setWidgetResizable(true); scroll->setWidget(side_content); scroll->setMinimumWidth(460); scroll->setMaximumWidth(510); right->addWidget(scroll,1);
        auto* connection = new QGroupBox(QStringLiteral("1 · 当前状态与参考点")); auto* connection_layout = new QVBoxLayout(connection); side->addWidget(connection);
        auto* reference_actions = new QHBoxLayout; connection_layout->addLayout(reference_actions);
        sync_ = button(reference_actions,options_.backend == "manual_unconfirmed" ? QStringLiteral("登记当前指令状态") : QStringLiteral("读取 / 同步驱动状态"),[this]() { sync_state(); });
        calibrate_ = button(reference_actions,QStringLiteral("设置幕面四个参考点"),[this]() { start_calibration(); });
        auto* rod_group = new QGroupBox(QStringLiteral("2 · 点动 / 准备发送的目标值")); auto* rod_layout = new QVBoxLayout(rod_group); side->addWidget(rod_group);
        rod_ = new QComboBox;
        std::vector<std::string> configured_rods;
        for (const auto& axis : session_.config().axes) {
            if (std::find(configured_rods.begin(), configured_rods.end(), axis.rod) == configured_rods.end()) {
                configured_rods.push_back(axis.rod); rod_->addItem(rod_label(axis.rod), q(axis.rod));
            }
        }
        rod_layout->addWidget(rod_); axis_note_=new QLabel; axis_note_->setWordWrap(true); rod_layout->addWidget(axis_note_);
        show_all_axes_=new QCheckBox(QStringLiteral("显示全部电机轴（记录始终包含全部轴）")); rod_layout->addWidget(show_all_axes_);
        connect(show_all_axes_,&QCheckBox::toggled,this,[this]() { update_controls(); });
        axis_form_ = new QFormLayout; auto* axis_form = axis_form_; rod_layout->addLayout(axis_form);
        for (std::size_t i=0; i<session_.config().axes.size(); ++i) {
            const auto& axis=session_.config().axes[i]; auto* row = new QWidget; auto* row_layout = new QHBoxLayout(row); row_layout->setContentsMargins(0,0,0,0);
            auto* spin = new QDoubleSpinBox; spin->setDecimals(6); spin->setRange(axis.min,axis.max); spin->setSingleStep(axis.jog_step); spin->setValue(axis.initial);
            axis_spins_.push_back(spin); row_layout->addWidget(spin,1);
            for (double direction : {-1.0,1.0}) {
                auto* jog_button=button(row_layout,direction<0?QStringLiteral("−"):QStringLiteral("＋"),[this,i,direction]() { jog(i,direction); });
                jog_button->setMaximumWidth(32); jog_buttons_.push_back(jog_button);
            }
            axis_form->addRow(q(axis.id)+" / "+q(axis.unit),row);
            axis_rows_.push_back(row);
            connect(spin,QOverload<double>::of(&QDoubleSpinBox::valueChanged),this,[this]() {
                editor_dirty_=true; settled_->setChecked(false); message(QStringLiteral("命令字段已修改，请先登记 / 提交再采集。"));
            });
        }
        for (std::size_t i=0; i<session_.config().slides.size(); ++i) {
            const auto& slide = session_.config().slides[i];
            auto* row = new QWidget; auto* row_layout = new QHBoxLayout(row); row_layout->setContentsMargins(0,0,0,0);
            auto* spin=new QDoubleSpinBox; spin->setDecimals(6);
            spin->setRange(slide.controllable?slide.min:-1000000,slide.controllable?slide.max:1000000);
            if (slide.controllable) spin->setSingleStep(slide.jog_step);
            spin->setValue(slide.value); slide_spins_.push_back(spin); row_layout->addWidget(spin,1);
            if (slide.controllable) for (double direction : {-1.0,1.0}) {
                auto* b = button(row_layout,direction<0?QStringLiteral("−"):QStringLiteral("＋"),[this,i,direction]() { jog_slide(i,direction); });
                b->setMaximumWidth(32); slide_jog_buttons_.push_back(b);
            }
            axis_form->addRow((slide.id=="wusong_slide"?QStringLiteral("武松滑轨"):slide.id=="tiger_slide"?QStringLiteral("老虎滑轨"):q(slide.id))+" / "+q(slide.unit),row);
            connect(spin,QOverload<double>::of(&QDoubleSpinBox::valueChanged),this,[this]() {
                editor_dirty_=true; settled_->setChecked(false); message(QStringLiteral("滑台字段已修改，请先登记当前状态。"));
            });
        }
        apply_=button(rod_layout,options_.backend=="manual_unconfirmed"?QStringLiteral("登记以上命令（未确认）"):QStringLiteral("提交以上整组目标"),[this]() { apply_editors(); });
        auto* plan_group=new QGroupBox(QStringLiteral("可选 · 预设采样列表")); auto* plan_layout=new QVBoxLayout(plan_group); side->addWidget(plan_group);
        plan_label_=new QLabel; plan_label_->setWordWrap(true); plan_layout->addWidget(plan_label_);
        auto* plan_actions = new QHBoxLayout; plan_layout->addLayout(plan_actions);
        execute_=button(plan_actions,QStringLiteral("执行当前采样组"),[this]() { execute_plan(); });
        if (options_.backend=="manual_unconfirmed") execute_->setToolTip(QStringLiteral("只登记列表中的命令；需要在实际点动工具中执行后再确认停稳。"));
        skip_=button(plan_actions,QStringLiteral("跳过本组"),[this]() { skip_point(); });
        auto_next_=new QCheckBox(QStringLiteral("保存后自动执行下一组")); auto_next_->setChecked(false);
        auto_next_->setEnabled(options_.backend!="manual_unconfirmed"); plan_layout->addWidget(auto_next_);
        side->addStretch();
        auto* record_group=new QGroupBox(QStringLiteral("3 · 停稳 → 点击连接点 → 确认记录"));
        auto* record_layout=new QVBoxLayout(record_group); right->addWidget(record_group);
        settled_=new QCheckBox(QStringLiteral("我已观察机构停稳，并保持不动")); record_layout->addWidget(settled_);
        connect(settled_,&QCheckBox::toggled,this,[this]() { update_controls(); });
        freeze_=button(record_layout,QStringLiteral("冻结新画面 → 在幕布上点击连接点"),[this]() { freeze_frame(); });
        coordinate_ = new QLabel(QStringLiteral("等待冻结画面并点击连接点。")); coordinate_->setWordWrap(true); coordinate_->setMinimumHeight(50);
        coordinate_->setStyleSheet("font-weight:600;color:#075f52;background:#eef7f4;padding:8px;"); record_layout->addWidget(coordinate_);
        adopted_note_=new QLabel; adopted_note_->setWordWrap(true); adopted_note_->setTextInteractionFlags(Qt::TextSelectableByMouse);
        QFont readback_font = adopted_note_->font(); readback_font.setPointSize(9); adopted_note_->setFont(readback_font);
        record_layout->addWidget(adopted_note_);
        confirmed_sample_=new QCheckBox(QStringLiteral("我已核对右侧指令及取点坐标")); record_layout->addWidget(confirmed_sample_);
        connect(confirmed_sample_,&QCheckBox::toggled,this,[this]() { update_controls(); });
        save_=button(record_layout,QStringLiteral("确认并记录本组数据和照片"),[this]() { save_sample(); });
        save_->setStyleSheet("QPushButton {font-weight:600;padding:7px;} QPushButton:enabled {background:#087f6d;color:white;} QPushButton:disabled {background:#e3e8e6;color:#81928b;}");
        auto* capture_actions = new QHBoxLayout; record_layout->addLayout(capture_actions);
        cancel_=button(capture_actions,QStringLiteral("取消取点 / 重拍"),[this]() { cancel_capture(); });
        pause_=button(capture_actions,QStringLiteral("暂停发令"),[this]() { paused_=!paused_; auto_next_->setChecked(false); update_controls(); });
        auto* note=new QLabel(QStringLiteral("暂停发令不等于电机急停。实际急停由控制板提供。")); note->setWordWrap(true); record_layout->addWidget(note);
        status_=new QLabel; status_->setWordWrap(true); status_->setMinimumHeight(50); status_->setStyleSheet("background:#edf4f2;color:#183f37;padding:10px;border-radius:6px;"); layout->addWidget(status_);
        connect(rod_,QOverload<int>::of(&QComboBox::currentIndexChanged),this,[this]() { settled_->setChecked(false); canvas_->update(); update_controls(); });
    }
public:
    CaptureWindow(Options options, CaptureConfig config) : options_(std::move(options)),
        session_(options_.session,std::move(config),options_.backend), smoke_(!options_.smoke.empty()) {
        build_ui();
        Json source{{"version",1},{"source",options_.demo?"synthetic_demo":options_.camera>=0?"usb_camera":!options_.frame_url.empty()?"http_live_gateway":"offline_image"},
            {"frame_url",options_.frame_url},{"top_url",options_.top_url},{"top_view_role","monitor only; not synchronized or used for XY"},
            {"camera_index",options_.camera},{"image_file",options_.image.u8string()},
            {"timestamp_meaning","host frame-read/freeze time; not camera exposure time"},
            {"buffer_discard_frames",3}};
        write_atomic(session_.directory()/"capture_source.json",source.dump(2)+"\n");
        if (options_.backend=="external") {
            exchange_dir_=fs::absolute(options_.exchange)/session_.session_id();
            fs::create_directories(exchange_dir_/"requests"); fs::create_directories(exchange_dir_/"acks");
            message(QStringLiteral("先启动板端驱动和电脑适配器，再读取状态。交换目录：")+q(exchange_dir_.u8string()));
        } else { sync_state(); }
        if (options_.camera>=0) camera_=std::make_unique<CameraFeed>(options_.camera);
        if (!options_.frame_url.empty()) http_camera_=std::make_unique<HttpFrameFeed>(options_.frame_url);
        if (!options_.top_url.empty()) top_camera_=std::make_unique<HttpFrameFeed>(options_.top_url);
        if (!options_.image.empty()) {
            latest_=cv::imread(options_.image.string(),cv::IMREAD_COLOR);
            if (latest_.empty()) throw std::runtime_error("Cannot read --image");
            ++frame_number_; frame_read_ms_=monotonic_ms(); frame_read_at_=capture_utc_now();
        }
        connect(&timer_,&QTimer::timeout,this,[this]() { guarded([&]() { poll_ack(); refresh_frame(); }); });
        timer_.start(40); refresh_frame(); update_controls();
        if (!options_.preview.empty()) {
            auto* preview_timer=new QTimer(this); const auto started=monotonic_ms();
            connect(preview_timer,&QTimer::timeout,this,[this,preview_timer,started]() {
                if (!source_fault_ && !latest_.empty() && monotonic_ms()-started>=2500) {
                    const bool saved=grab().save(q(options_.preview.u8string()));
                    std::cout << (saved?"LIVE_PREVIEW_PASS":"LIVE_PREVIEW_SAVE_FAILED") << '\n';
                    preview_timer->stop(); QApplication::exit(saved?0:2);
                } else if(monotonic_ms()-started>12000) {
                    std::cerr << "Live preview sources did not become fresh\n"; preview_timer->stop(); QApplication::exit(2);
                }
            });
            preview_timer->start(100);
        }
    }
    void run_smoke() {
        // Exercise the same reference selection, point selection and persistence paths.
        QTimer::singleShot(100,this,[this]() {
            try {
                start_calibration();
                for (auto point : std::array<cv::Point2d,4>{{{80,550},{880,550},{880,50},{80,50}}}) on_pixel(point);
                if (!geometry_.valid()) throw std::runtime_error("Smoke: calibration failed");
                refresh_frame();
                if (!canvas_->rectified()) throw std::runtime_error("Smoke: curtain preview is not rectified");
                jog_slide(0,1);
                if (std::abs(session_.adopted_slides().at("wusong_slide")-0.05)>1e-8)
                    throw std::runtime_error("Smoke: slide jog was not adopted");
                if (options_.backend=="manual_unconfirmed") {
                    slide_spins_.front()->setValue(0.1); settled_->setChecked(true);
                    if (freeze_->isEnabled()) throw std::runtime_error("Smoke: edited slide did not invalidate capture");
                    apply_editors();
                }
                execute_plan(); settled_->setChecked(true); freeze_frame();
                QTimer::singleShot(150,this,[this]() {
                    try {
                        if (phase_!=Phase::Frozen) throw std::runtime_error("Smoke: no fresh frozen frame");
                        auto expected=geometry_.to_stage(demo_point(selected_rod()));
                        const auto click = canvas_->display_point(demo_point(selected_rod()));
                        QMouseEvent event(QEvent::MouseButtonPress,click,Qt::LeftButton,Qt::LeftButton,Qt::NoModifier);
                        QApplication::sendEvent(canvas_,&event);
                        save_sample();
                        if (saved_count_!=0 || save_->isEnabled()) throw std::runtime_error("Smoke: record allowed before confirmation");
                        confirmed_sample_->setChecked(true);
                        if (!grab().save(q(options_.smoke.u8string()))) throw std::runtime_error("Smoke: screenshot failed");
                        save_sample();
                        if (saved_count_!=1 || !fs::exists(session_.directory()/"frames/sample_000001.png"))
                            throw std::runtime_error("Smoke: sample/image was not committed");
                        std::ifstream stream(session_.directory()/"samples.jsonl"); std::string line; std::getline(stream,line);
                        if (line.empty()) throw std::runtime_error("Smoke: no JSONL sample");
                        const auto saved = Json::parse(line);
                        std::ifstream calibration_stream(session_.directory()/(calibration_id_+".json"));
                        Json calibration_saved; calibration_stream >> calibration_saved;
                        std::ifstream snapshot_stream(session_.directory()/"config.snapshot.json");
                        Json snapshot_saved; snapshot_stream >> snapshot_saved;
                        if (saved.at("reference_view") != session_.config().reference_view ||
                            calibration_saved.at("reference_view") != session_.config().reference_view ||
                            snapshot_saved.at("reference_view") != session_.config().reference_view)
                            throw std::runtime_error("Smoke: coordinate view was not preserved");
                        if (std::abs(saved.at("stage_mm").at("x").get<double>()-expected.x)>1e-5 ||
                            std::abs(saved.at("stage_mm").at("y").get<double>()-expected.y)>1e-5 ||
                            saved.at("seq").get<std::uint64_t>()!=state_seq_ ||
                            saved.at("frame_read_at").is_null() || !saved.at("state").at("feedback").is_null())
                            throw std::runtime_error("Smoke: stored point/state/frame metadata is mismatched");
                        if (options_.backend=="manual_unconfirmed" &&
                            (saved.at("state").at("confirmed").get<bool>() ||
                             saved.at("state").at("slides")[0].at("value").get<double>()!=0.1))
                            throw std::runtime_error("Smoke: manual record changed its confirmation/slide state");
                        std::cout << "capture_gui_workflow passed; session=" << session_.directory().string() << '\n';
                        QApplication::exit(0);
                    } catch (const std::exception& error) { std::cerr<<error.what()<<'\n'; QApplication::exit(2); }
                });
            } catch (const std::exception& error) { std::cerr<<error.what()<<'\n'; QApplication::exit(2); }
        });
    }
};
}

int main(int argc,char** argv) {
    try {
        auto options=parse_options(argc,argv);
        // Qt consumes only its own default argv; CLI flags are parsed above.
        QApplication app(argc,argv); app.setApplicationName("Shadow Capture");
        app.setStyle("Fusion"); app.setFont(QFont(QStringLiteral("Noto Sans CJK SC"),10));
        auto config=load_capture_config(fs::u8path(options.config));
        if (!options.reference_view.empty()) {
            config.reference_view = options.reference_view;
            config.source_json.clear();
        }
        if (options.backend=="external" && (std::any_of(config.axes.begin(),config.axes.end(),
            [](const CaptureAxis& axis) { return axis.unit=="demo"; }) ||
            std::any_of(config.slides.begin(),config.slides.end(),[](const CaptureSlide& slide) { return slide.unit=="demo"; })))
            throw std::runtime_error("External driver cannot use demo units; provide the real axis configuration");
        if (options.width!=0 || options.height!=0) {
            if (options.width!=0) config.stage_width_mm=options.width;
            if (options.height!=0) config.stage_height_mm=options.height;
            config.reference_points_mm={{{{0,0}},{{config.stage_width_mm,0}},{{config.stage_width_mm,config.stage_height_mm}},{{0,config.stage_height_mm}}}};
            validate_capture_config(config);
            config.source_json.clear(); // Snapshot must contain the effective overridden dimensions.
        }
        CaptureWindow window(options,std::move(config)); window.show();
        if (!options.smoke.empty()) window.run_smoke();
        return app.exec();
    } catch (const std::exception& error) { std::cerr<<"shadow_capture: "<<error.what()<<'\n'; return 1; }
}
