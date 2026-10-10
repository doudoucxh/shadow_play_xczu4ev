#include "pose_cnn_accel.h"

#include <cstdlib>
#include <iostream>
#include <vector>

static pose_q_word_t pack_bytes(const std::vector<int> &values, int start)
{
    pose_q_word_t word = 0;
    for (int lane = 0; lane < 8; ++lane) {
        int index = start + lane;
        int value = index < (int)values.size() ? values[index] : 0;
        word.range(lane * 8 + 7, lane * 8) = value & 255;
    }
    return word;
}

static void pack_array(const std::vector<int> &values, pose_q_word_t *words)
{
    for (int start = 0; start < (int)values.size(); start += 8)
        words[start >> 3] = pack_bytes(values, start);
}

static int unpack_byte(const pose_q_word_t *words, int index)
{
    return words[index >> 3].range((index & 7) * 8 + 7, (index & 7) * 8);
}

static pose_q_word_t parameter(int bias, int multiplier = 1, int shift = 0)
{
    pose_q_word_t value = 0;
    value.range(31, 0) = (unsigned)bias;
    value.range(47, 32) = multiplier;
    value.range(55, 48) = shift;
    return value;
}

static int sat(int value)
{
    return value < 0 ? 0 : (value > 255 ? 255 : value);
}

static int test_pointwise()
{
    const int height = 2, width = 3, inputs = 16, outputs = 9;
    const int output_stride = 16;
    std::vector<int> input_values(height * width * inputs);
    std::vector<int> weight_values(outputs * inputs);
    for (int i = 0; i < (int)input_values.size(); ++i)
        input_values[i] = (i * 7 + 3) % 23;
    for (int i = 0; i < (int)weight_values.size(); ++i)
        weight_values[i] = (i * 5 + 1) % 7 - 3;

    static pose_q_word_t input[POSE_Q_MAX_FEATURE_WORDS] = {};
    static pose_q_word_t weights[POSE_Q_MAX_WEIGHT_WORDS] = {};
    static pose_q_word_t params[POSE_Q_MAX_CHANNELS] = {};
    static pose_q_word_t output[POSE_Q_MAX_FEATURE_WORDS] = {};
    static pose_q_word_t dummy[POSE_Q_MAX_FEATURE_WORDS] = {};
    pack_array(input_values, input);
    pack_array(weight_values, weights);
    for (int oc = 0; oc < outputs; ++oc)
        params[oc] = parameter(oc - 4);

    pose_cnn_accel(dummy, input, dummy, dummy, dummy, weights, params, dummy,
                   output, POSE_CNN_POINTWISE, height, width, inputs, outputs,
                   1, 5, 0, 97, 0, 0, 0, 0, 0);
    int failures = 0;
    for (int pixel = 0; pixel < height * width; ++pixel) {
        for (int oc = 0; oc < outputs; ++oc) {
            int expected = oc - 4;
            for (int ic = 0; ic < inputs; ++ic)
                expected += (input_values[pixel * inputs + ic] - 5) *
                            weight_values[oc * inputs + ic];
            expected = sat(expected + 97);
            int actual = unpack_byte(output, pixel * output_stride + oc);
            if (actual != expected)
                ++failures;
        }
        for (int oc = outputs; oc < output_stride; ++oc)
            if (unpack_byte(output, pixel * output_stride + oc) != 0)
                ++failures;
    }
    return failures;
}

static int test_depthwise_pointwise()
{
    const int height = 4, width = 5, channels = 16;
    std::vector<int> input_values(height * width * channels);
    std::vector<int> dw_weight_values(channels * 9);
    std::vector<int> pw_weight_values(channels * channels);
    for (int i = 0; i < (int)input_values.size(); ++i)
        input_values[i] = (i * 3 + 2) % 17;
    for (int i = 0; i < (int)dw_weight_values.size(); ++i)
        dw_weight_values[i] = (i * 5) % 5 - 2;
    for (int i = 0; i < (int)pw_weight_values.size(); ++i)
        pw_weight_values[i] = (i * 7) % 3 - 1;

    static pose_q_word_t input[POSE_Q_MAX_FEATURE_WORDS] = {};
    static pose_q_word_t dw_weights[(POSE_Q_MAX_CHANNELS * 9 + 7) / 8] = {};
    static pose_q_word_t pw_weights[POSE_Q_MAX_WEIGHT_WORDS] = {};
    static pose_q_word_t dw_params[POSE_Q_MAX_CHANNELS] = {};
    static pose_q_word_t pw_params[POSE_Q_MAX_CHANNELS] = {};
    static pose_q_word_t output[POSE_Q_MAX_FEATURE_WORDS] = {};
    static pose_q_word_t dummy[POSE_Q_MAX_FEATURE_WORDS] = {};
    pack_array(input_values, input);
    pack_array(dw_weight_values, dw_weights);
    pack_array(pw_weight_values, pw_weights);
    for (int c = 0; c < channels; ++c) {
        dw_params[c] = parameter(c % 3 - 1);
        pw_params[c] = parameter(c % 5 - 2);
    }

    pose_cnn_accel(dummy, input, dummy, dw_weights, dw_params, pw_weights,
                   pw_params, input, output, POSE_CNN_DW_PW, height, width,
                   channels, channels, 1, 8, 8, 0, 8, 1, 0, 1, 1);
    int failures = 0;
    for (int y = 0; y < height; ++y) {
        for (int x = 0; x < width; ++x) {
            int dw[channels];
            for (int c = 0; c < channels; ++c) {
                int accum = c % 3 - 1;
                for (int ky = 0; ky < 3; ++ky) {
                    for (int kx = 0; kx < 3; ++kx) {
                        int iy = y + ky - 1, ix = x + kx - 1;
                        if (iy >= 0 && iy < height && ix >= 0 && ix < width)
                            accum +=
                                (input_values[(iy * width + ix) * channels + c] - 8) *
                                dw_weight_values[c * 9 + ky * 3 + kx];
                    }
                }
                dw[c] = sat(accum + 8);
            }
            for (int oc = 0; oc < channels; ++oc) {
                int accum = oc % 5 - 2;
                for (int ic = 0; ic < channels; ++ic)
                    accum += (dw[ic] - 8) *
                             pw_weight_values[oc * channels + ic];
                if (accum < 0)
                    accum = 0;
                int residual = input_values[(y * width + x) * channels + oc] - 8;
                int expected = sat(accum + residual);
                int actual = unpack_byte(output, (y * width + x) * channels + oc);
                if (actual != expected)
                    ++failures;
            }
        }
    }
    return failures;
}

static int test_upsample_add()
{
    const int height = 2, width = 3, channels = 16;
    const int out_height = height * 2, out_width = width * 2;
    std::vector<int> input_values(height * width * channels);
    std::vector<int> residual_values(out_height * out_width * channels);
    for (int i = 0; i < (int)input_values.size(); ++i)
        input_values[i] = (i * 3) % 31;
    for (int i = 0; i < (int)residual_values.size(); ++i)
        residual_values[i] = (i * 5) % 29;
    static pose_q_word_t input[POSE_Q_MAX_FEATURE_WORDS] = {};
    static pose_q_word_t residual[POSE_Q_MAX_FEATURE_WORDS] = {};
    static pose_q_word_t params[POSE_Q_MAX_CHANNELS] = {};
    static pose_q_word_t output[POSE_Q_MAX_FEATURE_WORDS] = {};
    static pose_q_word_t dummy[POSE_Q_MAX_FEATURE_WORDS] = {};
    pack_array(input_values, input);
    pack_array(residual_values, residual);
    params[0] = parameter(0);
    pose_cnn_accel(dummy, input, dummy, dummy, params, dummy, dummy, residual,
                   output, POSE_CNN_UPSAMPLE_ADD, height, width, channels,
                   channels, 1, 7, 0, 3, 11, 1, 0, 0, 0);
    int failures = 0;
    for (int y = 0; y < out_height; ++y) {
        for (int x = 0; x < out_width; ++x) {
            for (int c = 0; c < channels; ++c) {
                int source = input_values[((y >> 1) * width + (x >> 1)) * channels + c] - 7;
                int residual_value = residual_values[(y * out_width + x) * channels + c] - 11;
                int expected = sat(source + residual_value + 3);
                int actual = unpack_byte(output, (y * out_width + x) * channels + c);
                if (actual != expected)
                    ++failures;
            }
        }
    }
    return failures;
}

static int test_stem()
{
    const int height = 6, width = 8, outputs = 16;
    const int out_height = 3, out_width = 4;
    std::vector<int> raw(height * width * 3);
    std::vector<int> lut(256);
    std::vector<int> weights(outputs * 27);
    for (int i = 0; i < (int)raw.size(); ++i)
        raw[i] = (i * 11 + 5) & 255;
    for (int i = 0; i < 256; ++i)
        lut[i] = i;
    for (int i = 0; i < (int)weights.size(); ++i)
        weights[i] = (i * 3) % 5 - 2;
    static pose_q_word_t raw_words[POSE_Q_MAX_RAW_WORDS] = {};
    static pose_q_word_t lut_words[32] = {};
    static pose_q_word_t weight_words[POSE_Q_MAX_WEIGHT_WORDS] = {};
    static pose_q_word_t params[POSE_Q_MAX_CHANNELS] = {};
    static pose_q_word_t output[POSE_Q_MAX_FEATURE_WORDS] = {};
    static pose_q_word_t dummy[POSE_Q_MAX_FEATURE_WORDS] = {};
    pack_array(raw, raw_words);
    pack_array(lut, lut_words);
    pack_array(weights, weight_words);
    for (int c = 0; c < outputs; ++c)
        params[c] = parameter(c - 8);
    pose_cnn_accel(raw_words, dummy, lut_words, dummy, dummy, weight_words,
                   params, dummy, output, POSE_CNN_STEM, height, width, 3,
                   outputs, 2, 128, 0, 100, 0, 0, 0, 1, 0);
    int failures = 0;
    for (int oy = 0; oy < out_height; ++oy) {
        for (int ox = 0; ox < out_width; ++ox) {
            for (int oc = 0; oc < outputs; ++oc) {
                int accum = oc - 8;
                for (int ky = 0; ky < 3; ++ky) {
                    for (int kx = 0; kx < 3; ++kx) {
                        for (int ic = 0; ic < 3; ++ic) {
                            int iy = oy * 2 + ky - 1;
                            int ix = ox * 2 + kx - 1;
                            int value = 128;
                            if (iy >= 0 && iy < height && ix >= 0 && ix < width)
                                value = raw[(iy * width + ix) * 3 + (2 - ic)];
                            int kernel = (ky * 3 + kx) * 3 + ic;
                            accum += (value - 128) * weights[oc * 27 + kernel];
                        }
                    }
                }
                int expected = sat(accum + 100);
                int actual = unpack_byte(output, (oy * out_width + ox) * outputs + oc);
                if (actual != expected)
                    ++failures;
            }
        }
    }
    return failures;
}

int main()
{
    int pointwise = test_pointwise();
    int fused = test_depthwise_pointwise();
    int upsample = test_upsample_add();
    int stem = test_stem();
    int failures = pointwise + fused + upsample + stem;
    std::cout << "POSE_CNN_INT8_CSIM failures=" << failures
              << " pointwise=" << pointwise << " fused=" << fused
              << " upsample=" << upsample << " stem=" << stem << std::endl;
    return failures == 0 ? 0 : 1;
}
