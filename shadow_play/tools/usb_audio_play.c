/* Standalone 48 kHz stereo MP3 player; no motion or camera interfaces.
 * Build with TinyALSA and minimp3; see docs/usb_audio_20261014.md.
 */
#define MINIMP3_IMPLEMENTATION
#define MINIMP3_ONLY_MP3
#include "minimp3_ex.h"
#include <tinyalsa/pcm.h>
#include <errno.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static double now_seconds(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec + ts.tv_nsec / 1e9;
}

int main(int argc, char **argv)
{
    int check = argc == 3 && strcmp(argv[1], "--check") == 0;
    if (!check && argc != 5) {
        fprintf(stderr, "Usage: %s --check FILE.mp3 | CARD DEVICE GAIN FILE.mp3\n", argv[0]);
        return 2;
    }
    unsigned long card = 0, device = 0;
    double gain = 0;
    char *end;
    if (!check) {
        errno = 0;
        card = strtoul(argv[1], &end, 10);
        if (errno || end == argv[1] || *end || card > 31) return 2;
        device = strtoul(argv[2], &end, 10);
        if (errno || end == argv[2] || *end || device > 31) return 2;
        gain = strtod(argv[3], &end);
        if (errno || end == argv[3] || *end || !isfinite(gain) || gain <= 0 || gain > 1) return 2;
    }
    mp3dec_t decoder;
    mp3dec_file_info_t audio = {0};
    int result = mp3dec_load(&decoder, argv[argc - 1], &audio, NULL, NULL);
    if (result || !audio.samples || audio.hz != 48000 || audio.channels != 2 || audio.samples % 2) {
        fprintf(stderr, "Decode failed or input is not 48000 Hz stereo: code=%d, hz=%d, channels=%d\n",
                result, audio.hz, audio.channels);
        free(audio.buffer);
        return 1;
    }
    size_t total = audio.samples / 2;
    printf("DECODE_OK frames=%zu duration=%.6f rate=48000 channels=2\n", total, total / 48000.0);
    fflush(stdout);
    if (check) { free(audio.buffer); return 0; }
    for (size_t i = 0; i < audio.samples; ++i)
        audio.buffer[i] = (mp3d_sample_t)(audio.buffer[i] * gain);
    struct pcm_config config = {
        .channels = 2, .rate = 48000, .period_size = 1024, .period_count = 4,
        .format = PCM_FORMAT_S16_LE, .start_threshold = 1024, .stop_threshold = 4096
    };
    struct pcm *pcm = pcm_open((unsigned int)card, (unsigned int)device, PCM_OUT | PCM_NORESTART, &config);
    if (!pcm || !pcm_is_ready(pcm)) {
        fprintf(stderr, "PCM open failed: %s\n", pcm ? pcm_get_error(pcm) : "allocation failed");
        if (pcm) pcm_close(pcm);
        free(audio.buffer);
        return 1;
    }
    printf("PLAY_START card=%lu device=%lu gain=%.3f\n", card, device, gain);
    fflush(stdout);
    double started = now_seconds();
    size_t written = 0;
    while (written < total) {
        unsigned int count = total - written > 1024 ? 1024 : (unsigned int)(total - written);
        int n = pcm_writei(pcm, audio.buffer + written * 2, count);
        if (n <= 0) {
            fprintf(stderr, "PCM write failed at frame %zu: %s\n", written, pcm_get_error(pcm));
            result = 1;
            break;
        }
        written += (size_t)n;
    }
    if (!result && pcm_drain(pcm) != 0) {
        fprintf(stderr, "PCM drain failed: %s\n", pcm_get_error(pcm));
        result = 1;
    }
    printf("PLAY_%s frames=%zu elapsed=%.3f\n", result ? "FAILED" : "COMPLETE", written, now_seconds() - started);
    pcm_close(pcm);
    free(audio.buffer);
    return result ? 1 : 0;
}
