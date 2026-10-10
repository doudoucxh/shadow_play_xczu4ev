#include "shadow/calibration_csv.hpp"
#include "shadow/motion_mapper.hpp"

#include <cmath>
#include <exception>
#include <iomanip>
#include <iostream>
#include <string>
#include <vector>

int main(int argc, char** argv) {
    if (argc != 2 || std::string(argv[1]) == "--help") {
        std::cerr << "Usage: mapper_demo <calibration.csv>\n"
                     "SIMULATION ONLY: prints an 8-second synthetic trace; no device I/O.\n";
        return argc == 2 ? 0 : 2;
    }
    try {
        const auto axes = shadow::load_calibration_csv(argv[1]);
        std::vector<double> initial;
        for (const auto& axis : axes) initial.push_back(axis.neutral_deg);
        // Neutral initialization is justified here by simulation, not hardware.
        shadow::MotionMapper mapper(axes, initial);
        std::cerr << "SIMULATION ONLY. 0-4s: generated poses; 2-2.2s: out-of-range\n"
                     "right-hand target; after 4s: no new input, then neutral return.\n";
        std::cout << "time_s,axis_id,rod,angle_deg,limited_target_deg,input_state,"
                     "input_clamped,angle_limited,speed_limited\n";
        std::cout << std::fixed << std::setprecision(6);
        constexpr double pi = 3.14159265358979323846;
        for (int tick = 0; tick <= 400; ++tick) {
            const double t = tick * 0.02;
            if (tick <= 200) {
                shadow::ShadowPose pose;
                for (std::size_t i = 0; i < shadow::kRodCount; ++i) {
                    const double phase = static_cast<double>(i) * 0.3;
                    pose.rods[i] = {0.75 * std::sin(pi * t + phase),
                                    0.4 * std::cos(pi * t + phase), true};
                }
                if (tick >= 100 && tick <= 110) pose.at(shadow::RodId::WusongRight).x = 2.5;
                mapper.submit_pose(pose, t);
            }
            for (const auto& axis : mapper.step(t)) {
                std::cout << t << ',' << axis.axis_id << ',' << shadow::rod_name(axis.rod)
                          << ',' << axis.angle_deg << ',' << axis.limited_target_deg << ','
                          << shadow::input_state_name(axis.input_state) << ','
                          << axis.input_clamped << ',' << axis.angle_limited << ','
                          << axis.speed_limited << '\n';
            }
        }
    } catch (const std::exception& error) {
        std::cerr << "Error: " << error.what() << '\n';
        return 1;
    }
    return 0;
}
