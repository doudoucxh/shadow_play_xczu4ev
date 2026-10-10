#pragma once
#include <cstddef>
#include <cstdint>
#include <memory>
#include <string>
#include <vector>

namespace shadow {
// Fixed to IPv4 loopback: intended for processes on the same PC/board.
// One datagram = one UTF-8 JSON frame or one ASCII control command.
class LoopbackUdp {
public:
    // port=0 creates a sending socket; nonzero binds a receive port exclusively.
    explicit LoopbackUdp(std::uint16_t port = 0);
    ~LoopbackUdp();
    LoopbackUdp(const LoopbackUdp&) = delete;
    LoopbackUdp& operator=(const LoopbackUdp&) = delete;
    void send(const std::string& message, std::uint16_t destination_port);
    std::vector<std::string> receive(std::size_t max_packets = 64);
    std::size_t oversized_dropped() const noexcept;
private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};
} // namespace shadow
