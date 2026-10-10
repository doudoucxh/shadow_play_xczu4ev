#include "shadow/udp.hpp"
#include <array>
#include <stdexcept>

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <ws2tcpip.h>
#else
#include <arpa/inet.h>
#include <cerrno>
#include <fcntl.h>
#include <sys/socket.h>
#include <unistd.h>
#endif

namespace shadow {
namespace {
constexpr std::size_t kMaxMessage = 16384;
#ifdef _WIN32
using Socket = SOCKET;
constexpr Socket kInvalid = INVALID_SOCKET;
void close_socket(Socket value) { closesocket(value); }
int error_number() { return WSAGetLastError(); }
bool would_block(int error) { return error == WSAEWOULDBLOCK; }
#else
using Socket = int;
constexpr Socket kInvalid = -1;
void close_socket(Socket value) { close(value); }
int error_number() { return errno; }
bool would_block(int error) { return error == EWOULDBLOCK || error == EAGAIN; }
#endif
std::runtime_error socket_error(const char* operation, int error) {
    return std::runtime_error(std::string(operation) + " failed (socket error " +
                              std::to_string(error) + ")");
}
sockaddr_in address(std::uint16_t port) {
    sockaddr_in result{};
    result.sin_family = AF_INET;
    result.sin_port = htons(port);
    result.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    return result;
}
} // namespace

struct LoopbackUdp::Impl {
    Socket socket = kInvalid;
    std::size_t oversized = 0;
#ifdef _WIN32
    bool winsock = false;
#endif
    ~Impl() {
        if (socket != kInvalid) close_socket(socket);
#ifdef _WIN32
        if (winsock) WSACleanup();
#endif
    }
};
LoopbackUdp::LoopbackUdp(std::uint16_t port) : impl_(new Impl) {
#ifdef _WIN32
    WSADATA data{};
    const int startup = WSAStartup(MAKEWORD(2, 2), &data);
    if (startup != 0) throw socket_error("WSAStartup", startup);
    impl_->winsock = true;
#endif
    impl_->socket = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    if (impl_->socket == kInvalid) throw socket_error("socket", error_number());
#ifdef _WIN32
    const BOOL exclusive = TRUE;
    if (setsockopt(impl_->socket, SOL_SOCKET, SO_EXCLUSIVEADDRUSE,
                   reinterpret_cast<const char*>(&exclusive), sizeof(exclusive)) != 0) {
        throw socket_error("exclusive bind option", error_number());
    }
    u_long nonblocking = 1;
    if (ioctlsocket(impl_->socket, FIONBIO, &nonblocking) != 0) {
        throw socket_error("nonblocking option", error_number());
    }
#else
    const int flags = fcntl(impl_->socket, F_GETFL, 0);
    if (flags < 0 || fcntl(impl_->socket, F_SETFL, flags | O_NONBLOCK) < 0) {
        throw socket_error("nonblocking option", error_number());
    }
#endif
    if (port != 0) {
        const auto local = address(port);
        if (bind(impl_->socket, reinterpret_cast<const sockaddr*>(&local), sizeof(local)) != 0) {
            throw socket_error("bind 127.0.0.1", error_number());
        }
    }
}
LoopbackUdp::~LoopbackUdp() = default;
void LoopbackUdp::send(const std::string& message, std::uint16_t destination_port) {
    if (destination_port == 0 || message.empty() || message.size() > kMaxMessage) {
        throw std::invalid_argument("UDP needs a nonzero port and 1..16384 message bytes");
    }
    const auto destination = address(destination_port);
    const auto count = sendto(impl_->socket, message.data(), static_cast<int>(message.size()), 0,
                              reinterpret_cast<const sockaddr*>(&destination), sizeof(destination));
    if (count < 0) throw socket_error("sendto", error_number());
    if (static_cast<std::size_t>(count) != message.size()) throw std::runtime_error("short UDP send");
}
std::vector<std::string> LoopbackUdp::receive(std::size_t max_packets) {
    std::vector<std::string> messages;
    std::array<char, 65536> buffer{};
    for (std::size_t i = 0; i < max_packets; ++i) {
        const auto count = recvfrom(impl_->socket, buffer.data(), static_cast<int>(buffer.size()),
                                    0, nullptr, nullptr);
        if (count < 0) {
            const int error = error_number();
            if (would_block(error)) break;
#ifndef _WIN32
            if (error == EINTR) continue;
#endif
            throw socket_error("recvfrom", error);
        }
        if (static_cast<std::size_t>(count) > kMaxMessage) {
            ++impl_->oversized;
            continue;
        }
        messages.emplace_back(buffer.data(), static_cast<std::size_t>(count));
    }
    return messages;
}
std::size_t LoopbackUdp::oversized_dropped() const noexcept { return impl_->oversized; }
} // namespace shadow
