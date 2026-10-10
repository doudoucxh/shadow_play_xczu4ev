#include "pose_cnn_accel.h"
#include "../../vitis/ov5640_hdmi/src/pose_model_int8_weights.h"

#include <fstream>
#include <iostream>
#include <vector>

template <size_t N>
static void load_words(const unsigned long long (&source)[N],
                       pose_q_word_t *destination)
{
    for (size_t index = 0; index < N; ++index)
        destination[index] = source[index];
}

static bool read_raw(const char *path, pose_q_word_t *destination)
{
    std::ifstream stream(path, std::ios::binary);
    std::vector<unsigned char> bytes(144 * 256 * 3);
    if (!stream.read(reinterpret_cast<char *>(bytes.data()), bytes.size()))
        return false;
    for (size_t index = 0; index < bytes.size(); index += 8) {
        pose_q_word_t word = 0;
        for (int lane = 0; lane < 8; ++lane)
            word.range(lane * 8 + 7, lane * 8) = bytes[index + lane];
        destination[index >> 3] = word;
    }
    return true;
}

static bool write_heatmap(const char *path, const pose_q_word_t *source)
{
    std::ofstream stream(path, std::ios::binary);
    if (!stream)
        return false;
    for (int index = 0; index < 36 * 64 * 16; ++index) {
        unsigned char value = source[index >> 3].range((index & 7) * 8 + 7,
                                                       (index & 7) * 8).to_uint();
        stream.write(reinterpret_cast<const char *>(&value), 1);
    }
    return !!stream;
}

int main(int argc, char **argv)
{
    if (argc != 3) {
        std::cerr << "usage: pose_model_csim input_bgr.bin output_heatmap.bin\n";
        return 2;
    }
    static pose_q_word_t raw[POSE_Q_MAX_RAW_WORDS] = {};
    static pose_q_word_t lut[32] = {};
    static pose_q_word_t dw_weights[(POSE_Q_MAX_CHANNELS * 9 + 7) / 8] = {};
    static pose_q_word_t pw_weights[POSE_Q_MAX_WEIGHT_WORDS] = {};
    static pose_q_word_t dw_params[POSE_Q_MAX_CHANNELS] = {};
    static pose_q_word_t pw_params[POSE_Q_MAX_CHANNELS] = {};
    static pose_q_word_t feature0[POSE_Q_MAX_FEATURE_WORDS] = {};
    static pose_q_word_t feature1[POSE_Q_MAX_FEATURE_WORDS] = {};
    static pose_q_word_t high[POSE_Q_MAX_FEATURE_WORDS] = {};
    static pose_q_word_t low_extra[POSE_Q_MAX_FEATURE_WORDS] = {};
    static pose_q_word_t heatmap[POSE_Q_MAX_FEATURE_WORDS] = {};

    if (!read_raw(argv[1], raw)) {
        std::cerr << "cannot read input\n";
        return 3;
    }
    load_words(pose_input_quant_lut_q, lut);
    load_words(pose_stem_w_q, pw_weights);
    load_words(pose_stem_p_q, pw_params);
    pose_cnn_accel(raw, feature0, lut, lut, lut, pw_weights, pw_params,
                   feature0, feature0, POSE_CNN_STEM, 144, 256, 3, 24, 2,
                   POSE_STEM_INPUT_ZP, 0, POSE_STEM_OUTPUT_ZP, 0, 0, 0, 1, 0);

#define POSE_HIGH_PW_RESIDUAL_ZP 0
#define POSE_HIGH_PW_RESIDUAL_MULT 0
#define POSE_HIGH_PW_RESIDUAL_SHIFT 0
#define POSE_LOW0_PW_RESIDUAL_ZP 0
#define POSE_LOW0_PW_RESIDUAL_MULT 0
#define POSE_LOW0_PW_RESIDUAL_SHIFT 0
#define RUN_DW_PW(src, dst, name, macro, h, w, in_ch, out_ch, stride_value, residual_value) \
    do { \
        load_words(name##_dw_w_q, dw_weights); \
        load_words(name##_dw_p_q, dw_params); \
        load_words(name##_pw_w_q, pw_weights); \
        load_words(name##_pw_p_q, pw_params); \
        pose_cnn_accel(raw, src, lut, dw_weights, dw_params, pw_weights, \
                       pw_params, src, dst, POSE_CNN_DW_PW, h, w, in_ch, \
                       out_ch, stride_value, macro##_DW_INPUT_ZP, \
                       macro##_DW_OUTPUT_ZP, macro##_PW_OUTPUT_ZP, \
                       residual_value ? macro##_PW_RESIDUAL_ZP : 0, \
                       residual_value ? macro##_PW_RESIDUAL_MULT : 0, \
                       residual_value ? macro##_PW_RESIDUAL_SHIFT : 0, \
                       1, residual_value); \
    } while (0)

    RUN_DW_PW(feature0, high, pose_high, POSE_HIGH, 72, 128, 24, 32, 2, 0);
    RUN_DW_PW(high, feature0, pose_highref0, POSE_HIGHREF0, 36, 64, 32, 32, 1, 1);
    RUN_DW_PW(feature0, high, pose_highref1, POSE_HIGHREF1, 36, 64, 32, 32, 1, 1);
    RUN_DW_PW(high, feature0, pose_low0, POSE_LOW0, 36, 64, 32, 48, 2, 0);
    RUN_DW_PW(feature0, feature1, pose_low1, POSE_LOW1, 18, 32, 48, 48, 1, 1);
    RUN_DW_PW(feature1, low_extra, pose_low2, POSE_LOW2, 18, 32, 48, 48, 1, 1);
    RUN_DW_PW(low_extra, feature0, pose_low3, POSE_LOW3, 18, 32, 48, 48, 1, 1);

    load_words(pose_context_w_q, pw_weights);
    load_words(pose_context_p_q, pw_params);
    pose_cnn_accel(raw, feature0, lut, lut, lut, pw_weights, pw_params,
                   feature0, feature1, POSE_CNN_POINTWISE, 18, 32, 48, 32, 1,
                   POSE_CONTEXT_INPUT_ZP, 0, POSE_CONTEXT_OUTPUT_ZP,
                   0, 0, 0, 1, 0);

    load_words(pose_merge_input_p_q, dw_params);
    pose_cnn_accel(raw, feature1, lut, lut, dw_params, lut, lut, high,
                   feature0, POSE_CNN_UPSAMPLE_ADD, 18, 32, 32, 32, 1,
                   POSE_MERGE_INPUT_ZP, 0, POSE_MERGE_OUTPUT_ZP,
                   POSE_MERGE_RESIDUAL_ZP, POSE_MERGE_RESIDUAL_MULT,
                   POSE_MERGE_RESIDUAL_SHIFT, 0, 0);

    RUN_DW_PW(feature0, feature1, pose_ref0, POSE_REF0, 36, 64, 32, 32, 1, 1);
    RUN_DW_PW(feature1, feature0, pose_ref1, POSE_REF1, 36, 64, 32, 32, 1, 1);
    RUN_DW_PW(feature0, feature1, pose_ref2, POSE_REF2, 36, 64, 32, 32, 1, 1);
#undef RUN_DW_PW
#undef POSE_HIGH_PW_RESIDUAL_ZP
#undef POSE_HIGH_PW_RESIDUAL_MULT
#undef POSE_HIGH_PW_RESIDUAL_SHIFT
#undef POSE_LOW0_PW_RESIDUAL_ZP
#undef POSE_LOW0_PW_RESIDUAL_MULT
#undef POSE_LOW0_PW_RESIDUAL_SHIFT

    load_words(pose_head_w_q, pw_weights);
    load_words(pose_head_p_q, pw_params);
    pose_cnn_accel(raw, feature1, lut, lut, lut, pw_weights, pw_params,
                   feature1, heatmap, POSE_CNN_POINTWISE, 36, 64, 32, 9, 1,
                   POSE_HEAD_INPUT_ZP, 0, POSE_HEAD_OUTPUT_ZP,
                   0, 0, 0, 0, 0);
    if (!write_heatmap(argv[2], heatmap)) {
        std::cerr << "cannot write output\n";
        return 4;
    }
    std::cout << "POSE_MODEL_CSIM PASS bytes=" << 36 * 64 * 16 << "\n";
    return 0;
}
