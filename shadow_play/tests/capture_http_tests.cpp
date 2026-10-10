#include "shadow/capture_http_feed.hpp"
#include <QCoreApplication>
#include <QTcpServer>
#include <QTcpSocket>
#include <QThread>
#include <functional>
#include <iostream>

namespace {
void require(bool ok, const char* message) { if (!ok) throw std::runtime_error(message); }
}
int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    try {
        QTcpServer server;
        require(server.listen(QHostAddress::LocalHost, 0), "cannot listen");
        std::vector<uchar> jpeg;
        cv::imencode(".jpg", cv::Mat(8, 8, CV_8UC3, cv::Scalar(10, 20, 30)), jpeg);
        QByteArray body(reinterpret_cast<const char*>(jpeg.data()), static_cast<int>(jpeg.size()));
        int producer = 1, replies = 0, age = 0;
        QObject::connect(&server, &QTcpServer::newConnection, &server, [&]() {
            auto* socket = server.nextPendingConnection();
            QObject::connect(socket, &QTcpSocket::readyRead, socket, [&, socket]() {
                socket->readAll();
                QByteArray header = "HTTP/1.1 200 OK\r\nContent-Type: image/jpeg\r\nConnection: close\r\nContent-Length: " +
                    QByteArray::number(body.size()) + "\r\nX-Frame-Id: " + QByteArray::number(producer) +
                    "\r\nX-Frame-Age-Ms: " + QByteArray::number(age) +
                    "\r\nX-Frame-Read-At: 2026-10-08T06:00:00Z\r\n\r\n";
                socket->write(header+body); socket->disconnectFromHost(); ++replies;
            });
            QObject::connect(socket, &QTcpSocket::disconnected, socket, &QObject::deleteLater);
        });
        shadow::HttpFrameFeed feed("http://127.0.0.1:" + std::to_string(server.serverPort()) + "/frame.jpg");
        std::uint64_t number=0, epoch=0; long long read_ms=0;
        std::string utc, error;
        auto pump = [&]() { app.processEvents(); feed.latest(number,read_ms,epoch,utc,error); QThread::msleep(2); };
        auto wait = [&](const std::function<bool()>& condition) {
            QElapsedTimer timer; timer.start();
            while (!condition() && timer.elapsed()<3500) pump();
            require(condition(), "HTTP test timed out");
        };
        wait([&]() { return number==1; });
        require(error.empty(), "first frame rejected"); const auto first_stamp=read_ms;
        wait([&]() { return replies>=5; });
        require(number==1 && read_ms==first_stamp, "duplicate response rejuvenated old frame");
        QElapsedTimer stopped; stopped.start();
        while (stopped.elapsed()<1550) pump();
        require(!error.empty() && number==1, "stopped producer was accepted as fresh");
        producer=2; wait([&]() { return number==2; });
        require(error.empty(), "fresh producer did not recover");
        const auto requested=feed.discard_buffer();
        for(int id=3; id<=5; ++id) {
            producer=id; const auto before=replies;
            wait([&]() { return replies>=before+2; });
            require(number==2 && epoch!=requested, "buffer discard accepted a skipped frame");
        }
        producer=6; wait([&]() { return number==3; });
        require(epoch==requested, "fresh epoch was not adopted");
        age=2000; producer=7; const auto before=replies;
        wait([&]() { return replies>=before+2; });
        require(!error.empty() && number==3, "stale gateway timestamp accepted");
        std::cout << "PASS: duplicate identities, stale producer, recovery, three-frame discard, stale header\n";
        return 0;
    } catch(const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
