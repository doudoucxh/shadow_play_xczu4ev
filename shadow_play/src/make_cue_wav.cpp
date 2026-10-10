#include <cmath>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>

namespace {
void word(std::ostream& out, std::uint16_t value) {
    const char bytes[] = {static_cast<char>(value & 255), static_cast<char>((value >> 8) & 255)};
    out.write(bytes, 2);
}
void dword(std::ostream& out, std::uint32_t value) {
    word(out, static_cast<std::uint16_t>(value & 65535));
    word(out, static_cast<std::uint16_t>(value >> 16));
}
}
int main(int argc, char** argv) {
    if (argc != 3) {
        std::cerr << "Usage: make_cue_wav NEW.wav DURATION_SECONDS\n"
                     "Creates PCM16 48kHz mono, quiet cue tone at each whole second.\n"
                     "TEST AUDIO ONLY; not narration/music for the actual performance.\n";
        return 2;
    }
    try {
        std::size_t used = 0;
        const std::string argument = argv[2];
        const double seconds = std::stod(argument, &used);
        if (used != argument.size() || !std::isfinite(seconds) || seconds < 0.02 || seconds > 3600) {
            throw std::invalid_argument("duration must be 0.02..3600 seconds");
        }
        std::ifstream existing(argv[1], std::ios::binary);
        if (existing.good()) throw std::runtime_error("output exists; choose a new filename");
        std::ofstream output(argv[1], std::ios::binary);
        if (!output) throw std::runtime_error("cannot create WAV output");
        constexpr std::uint32_t sample_rate = 48000;
        const auto frames = static_cast<std::uint32_t>(std::llround(seconds * sample_rate));
        const auto bytes = frames * 2U;
        output.write("RIFF", 4); dword(output, bytes + 36U); output.write("WAVEfmt ", 8);
        dword(output, 16); word(output, 1); word(output, 1); dword(output, sample_rate);
        dword(output, sample_rate * 2); word(output, 2); word(output, 16);
        output.write("data", 4); dword(output, bytes);
        constexpr double pi = 3.14159265358979323846;
        for (std::uint32_t index = 0; index < frames; ++index) {
            const double in_second = static_cast<double>(index % sample_rate) / sample_rate;
            double value = 0.0;
            if (in_second < 0.08) {
                const double envelope = std::sin(pi * in_second / 0.08);
                value = 0.12 * 32767.0 * envelope * std::sin(2.0 * pi * 880.0 * in_second);
            }
            word(output, static_cast<std::uint16_t>(static_cast<std::int16_t>(std::lround(value))));
        }
        output.flush();
        if (!output) throw std::runtime_error("WAV write failed");
        std::cout << "Created test cue WAV, " << static_cast<double>(frames) / sample_rate << " seconds.\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "Error: " << error.what() << '\n';
        return 1;
    }
}
