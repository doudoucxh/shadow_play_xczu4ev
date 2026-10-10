#include <Windows.h>
#include <atomic>
#include <chrono>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>
#include "CameraRemote_SDK.h"
#include "IDeviceCallback.h"
#include "CrDebugString.h"

namespace fs = std::filesystem;
using Clock = std::chrono::steady_clock;
std::atomic<bool> stop_requested{false};

BOOL WINAPI console_signal(DWORD event) {
    if(event == CTRL_C_EVENT || event == CTRL_BREAK_EVENT || event == CTRL_CLOSE_EVENT) {
        stop_requested = true;
        return TRUE;
    }
    return FALSE;
}

class Callback : public SCRSDK::IDeviceCallback {
public:
    std::atomic<bool> connected{false};
    std::atomic<CrInt32u> error{0};
    void OnConnected(SCRSDK::DeviceConnectionVersioin) override { connected = true; }
    void OnDisconnected(CrInt32u code) override { connected = false; error = code; }
    void OnError(CrInt32u code) override { error = code; }
};

void checked(SCRSDK::CrError error, const char* operation) {
    if(error) throw std::runtime_error(std::string(operation) + ": " + CrErrorString(error));
}

CrInt32u parse_ip(const std::string& text) {
    unsigned a, b, c, d; char extra;
    if(std::sscanf(text.c_str(), "%u.%u.%u.%u%c", &a, &b, &c, &d, &extra) != 4 ||
       a > 255 || b > 255 || c > 255 || d > 255) throw std::runtime_error("Invalid IPv4 address");
    return a | (b << 8) | (c << 16) | (d << 24);
}

void replace_file(const fs::path& path, const void* data, size_t size) {
    auto temp = path; temp += L".tmp";
    { std::ofstream stream(temp, std::ios::binary | std::ios::trunc);
      stream.write(static_cast<const char*>(data), static_cast<std::streamsize>(size));
      stream.flush();
      if(!stream) throw std::runtime_error("Cannot write preview file"); }
    // Readers see either the previous complete frame or the new complete frame.
    for(int attempt = 0; attempt < 20; ++attempt) {
        if(MoveFileExW(temp.c_str(), path.c_str(), MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH)) return;
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }
    throw std::runtime_error("Cannot publish preview file");
}

void status(const fs::path& folder, const char* state, unsigned frames, unsigned bytes = 0) {
    const auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::system_clock::now().time_since_epoch()).count();
    std::ostringstream data;
    data << "{\"state\":\"" << state << "\",\"frames\":" << frames
         << ",\"updated_unix_ms\":" << ms << ",\"jpeg_bytes\":" << bytes << "}\n";
    const auto text = data.str();
    replace_file(folder / "status.json", text.data(), text.size());
}

struct Camera {
    Callback callback;
    SCRSDK::ICrCameraObjectInfo* info = nullptr;
    SCRSDK::CrDeviceHandle handle = 0;
    bool initialized = false;
    ~Camera() {
        if(handle) {
            SCRSDK::Disconnect(handle);
            auto until = Clock::now() + std::chrono::seconds(3);
            while(callback.connected && Clock::now() < until) std::this_thread::sleep_for(std::chrono::milliseconds(50));
            SCRSDK::ReleaseDevice(handle);
        }
        if(info) info->Release();
        if(initialized) SCRSDK::Release();
    }
};

int main(int argc, char** argv) {
    fs::path output;
    unsigned frames = 0;
    std::string user, password;
    try {
        if(argc != 3 && argc != 6) throw std::runtime_error(
            "Usage: sony_liveview probe IP | sony_liveview live IP OUTPUT SECONDS FPS (credentials on stdin)");
        const bool probe = std::string(argv[1]) == "probe";
        if((probe && argc != 3) || (!probe && (argc != 6 || std::string(argv[1]) != "live")))
            throw std::runtime_error("Invalid arguments");
        const auto ip = parse_ip(argv[2]);
        int seconds = 0, fps = 0;
        if(!probe) {
            seconds = std::stoi(argv[4]); fps = std::stoi(argv[5]);
            if(seconds < 1 || seconds > 3600 || fps < 1 || fps > 15) throw std::runtime_error("Invalid duration or FPS");
            output = fs::u8path(argv[3]); fs::create_directories(output);
            status(output, "waiting_for_credentials", frames);
            if(!std::getline(std::cin, user) || !std::getline(std::cin, password) || user.empty() || password.empty())
                throw std::runtime_error("Camera access-authentication username and password are required");
        }
        Camera camera;
        camera.initialized = SCRSDK::Init(0);
        if(!camera.initialized) throw std::runtime_error("Sony SDK initialization failed");
        CrInt8u mac[6] = {};
        checked(SCRSDK::CreateCameraObjectInfoEthernetConnection(&camera.info,
            SCRSDK::CrCameraDeviceModel_ILCE_7M4, ip, mac, SCRSDK::CrSSHsupport_ON), "Create camera");
        char fingerprint[128] = {};
        CrInt32u fingerprint_size = 0;
        checked(SCRSDK::GetFingerprint(camera.info, fingerprint, &fingerprint_size), "Get camera fingerprint");
        if(fingerprint_size == 0 || fingerprint_size > sizeof(fingerprint)) throw std::runtime_error("Invalid fingerprint length");
        std::cout << "CAMERA_SSH_REACHABLE " << argv[2] << " fingerprint="
                  << std::string(fingerprint, fingerprint_size) << std::endl;
        if(probe) return 0;
        status(output, "connecting", frames);
        checked(SCRSDK::Connect(camera.info, &camera.callback, &camera.handle,
            SCRSDK::CrSdkControlMode_Remote, SCRSDK::CrReconnecting_OFF,
            user.c_str(), password.c_str(), fingerprint, fingerprint_size), "Connect");
        const auto deadline = Clock::now() + std::chrono::seconds(20);
        while(!camera.callback.connected && !camera.callback.error && Clock::now() < deadline)
            std::this_thread::sleep_for(std::chrono::milliseconds(50));
        SecureZeroMemory(password.data(), password.size()); password.clear();
        checked(camera.callback.error, "Connection callback");
        if(!camera.callback.connected) throw std::runtime_error("Camera connection timed out; release Imaging Edge Remote and retry");
        std::cout << "CAMERA_CONNECTED" << std::endl;
        SetConsoleCtrlHandler(console_signal, TRUE);
        const auto end = Clock::now() + std::chrono::seconds(seconds);
        auto last_success = Clock::now();
        std::vector<CrInt8u> buffer;
        SCRSDK::CrError last_error = 0;
        while(!stop_requested && Clock::now() < end && !fs::exists(output / "stop.request")) {
            if(!camera.callback.connected) throw std::runtime_error("Camera disconnected");
            auto next = Clock::now() + std::chrono::milliseconds(1000 / fps);
            SCRSDK::CrImageInfo info;
            auto error = SCRSDK::GetLiveViewImageInfo(camera.handle, &info);
            const auto size = info.GetBufferSize();
            if(!error && size > 0 && size <= 32 * 1024 * 1024) {
                buffer.resize(size);
                SCRSDK::CrImageDataBlock image;
                image.SetData(buffer.data()); image.SetSize(size);
                error = SCRSDK::GetLiveViewImage(camera.handle, &image);
                if(!error && image.GetImageSize() > 4 && image.GetImageSize() <= size) {
                    const auto* data = image.GetImageData();
                    if(data && data[0] == 0xff && data[1] == 0xd8) {
                        replace_file(output / "latest.jpg", data, image.GetImageSize());
                        ++frames;
                        status(output, "streaming", frames, image.GetImageSize());
                        last_success = Clock::now();
                        if(frames == 1 || frames % static_cast<unsigned>(fps * 10) == 0)
                            std::cout << "PREVIEW_FRAMES " << frames << " JPEG_BYTES " << image.GetImageSize() << std::endl;
                    }
                }
            }
            last_error = error;
            if(Clock::now() - last_success > std::chrono::seconds(15))
                throw std::runtime_error("No live-view frame within 15 seconds: " + CrErrorString(last_error));
            std::this_thread::sleep_until(next);
        }
        status(output, "stopped", frames);
        std::cout << "PREVIEW_STOPPED frames=" << frames << std::endl;
        return frames ? 0 : 2;
    } catch(const std::exception& error) {
        if(!password.empty()) SecureZeroMemory(password.data(), password.size());
        std::cerr << "ERROR " << error.what() << std::endl;
        if(!output.empty()) { try { status(output, "error", frames); } catch(...) {} }
        return 1;
    }
}
