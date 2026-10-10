#pragma once
#include "shadow/controller.hpp"
#include <cstdint>
#include <ostream>
#include <string>

namespace shadow {
// Actual hardware adapter must implement grouped updates and its own watchdog.
// The supplied implementations only export commands and never touch hardware.
class MotorBackend {
public:
    virtual ~MotorBackend() = default;
    virtual void send(const ControlTick& tick) = 0;
    virtual void shutdown() = 0;
};

class CsvMotorBackend final : public MotorBackend {
public:
    explicit CsvMotorBackend(std::ostream& stream);
    void send(const ControlTick& tick) override;
    void shutdown() override;
private:
    std::ostream& stream_;
};

// One whole control tick as JSON, without a trailing newline. Only angle_deg
// is an actuator target; input_state and limit flags are diagnostic fields.
// Throws before returning any data if the frame is invalid.
std::string serialize_motor_frame(const ControlTick& tick, std::uint64_t seq);

// Optional software handoff/trace format, not a hardware or AXI driver.
// Starts sequence numbers at 1 and flushes each complete JSON line.
class JsonlMotorBackend final : public MotorBackend {
public:
    explicit JsonlMotorBackend(std::ostream& stream);
    void send(const ControlTick& tick) override;
    void shutdown() override;
private:
    std::ostream& stream_;
    std::uint64_t next_sequence_ = 1;
    bool sequence_exhausted_ = false;
};
} // namespace shadow
