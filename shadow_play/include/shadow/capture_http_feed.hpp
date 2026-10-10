#pragma once
#include <QtNetwork>
#include <opencv2/imgcodecs.hpp>
#include <chrono>
#include <cstdint>
#include <string>

namespace shadow {
// Snapshot gateway reports producer age and an identity that changes only on a
// new source frame. Repeated HTTP responses cannot make an old frame fresh.
class HttpFrameFeed : public QObject {
    QNetworkAccessManager network_{this};
    QUrl url_;
    QNetworkReply* pending_ = nullptr;
    cv::Mat frame_;
    QByteArray identity_;
    std::uint64_t number_ = 0, requested_epoch_ = 0, frame_epoch_ = 0;
    long long read_ms_ = 0, next_request_ms_ = 0;
    int discard_ = 0;
    std::string utc_, error_ = "Waiting for a fresh gateway frame";
    static long long now() {
        return std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::steady_clock::now().time_since_epoch()).count();
    }
public:
    explicit HttpFrameFeed(const std::string& url) : url_(QString::fromStdString(url)) {
        if (url_.scheme() != "http" || url_.host().isEmpty() || !url_.userInfo().isEmpty())
            throw std::runtime_error("Frame gateway requires a local HTTP URL without credentials");
    }
    cv::Mat latest(std::uint64_t& number, long long& read_ms, std::uint64_t& epoch,
                   std::string& utc, std::string& error) {
        if (!pending_ && now() >= next_request_ms_) {
            QNetworkRequest request(url_);
            request.setAttribute(QNetworkRequest::CacheLoadControlAttribute, QNetworkRequest::AlwaysNetwork);
            const auto started = now();
            auto* reply = network_.get(request); pending_ = reply;
            QTimer::singleShot(1200, reply, [reply]() { if (!reply->isFinished()) reply->abort(); });
            connect(reply, &QNetworkReply::readyRead, reply, [reply]() {
                if (reply->bytesAvailable() > 8*1024*1024) reply->abort();
            });
            connect(reply, &QNetworkReply::finished, this, [this, reply, started]() {
                pending_ = nullptr; next_request_ms_ = now()+80;
                try {
                    if (reply->error() != QNetworkReply::NoError ||
                        reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt() != 200)
                        throw std::runtime_error("Frame gateway unavailable: " + reply->errorString().toStdString());
                    bool age_ok = false;
                    const auto age = reply->rawHeader("X-Frame-Age-Ms").toLongLong(&age_ok);
                    const auto id = reply->rawHeader("X-Frame-Id");
                    const auto utc = reply->rawHeader("X-Frame-Read-At");
                    if (!age_ok || age < 0 || age+now()-started > 1500 || id.isEmpty() || utc.isEmpty())
                        throw std::runtime_error("Gateway frame is stale or has no producer metadata");
                    if (id != identity_) {
                        const auto bytes = reply->readAll();
                        if (bytes.isEmpty() || bytes.size() > 8*1024*1024)
                            throw std::runtime_error("Invalid gateway image size");
                        std::vector<unsigned char> data(bytes.begin(), bytes.end());
                        auto frame = cv::imdecode(data, cv::IMREAD_COLOR);
                        if (frame.empty()) throw std::runtime_error("Invalid gateway JPEG");
                        identity_ = id;
                        if (discard_ > 0) --discard_;
                        else {
                            frame_ = std::move(frame); ++number_; frame_epoch_ = requested_epoch_;
                            read_ms_ = started-age; utc_ = utc.toStdString(); error_.clear();
                        }
                    }
                } catch (const std::exception& e) { error_ = e.what(); }
                reply->deleteLater();
            });
        }
        number = number_; read_ms = read_ms_; epoch = frame_epoch_; utc = utc_;
        error = (read_ms_ && now()-read_ms_ > 1500) ? "Frame producer stopped updating" : error_;
        return frame_.clone();
    }
    std::uint64_t discard_buffer() { discard_ = 3; return ++requested_epoch_; }
};
}
