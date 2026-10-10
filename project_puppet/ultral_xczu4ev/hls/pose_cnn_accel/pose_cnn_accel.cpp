#include "pose_cnn_accel.h"

static pose_q_data_t get_byte(pose_q_word_t word, int lane)
{
#pragma HLS INLINE
    return word.range(lane * 8 + 7, lane * 8);
}

static pose_q_weight_t get_weight(pose_q_word_t word, int lane)
{
#pragma HLS INLINE
    ap_uint<8> bits = word.range(lane * 8 + 7, lane * 8);
    return pose_q_weight_t(bits);
}

static pose_q_accum_t get_bias(pose_q_word_t parameter)
{
#pragma HLS INLINE
    ap_uint<32> bits = parameter.range(31, 0);
    return pose_q_accum_t(bits);
}

static ap_uint<16> get_multiplier(pose_q_word_t parameter)
{
#pragma HLS INLINE
    return parameter.range(47, 32);
}

static ap_uint<8> get_shift(pose_q_word_t parameter)
{
#pragma HLS INLINE
    return parameter.range(55, 48);
}

static ap_int<32> round_shift(ap_int<64> product, ap_uint<8> shift)
{
#pragma HLS INLINE
    if (shift == 0)
        return (ap_int<32>)product;
    ap_int<64> magnitude = product;
    if (product < 0)
        magnitude = -product;
    ap_int<64> rounded = (magnitude + ((ap_int<64>)1 << (shift - 1))) >> shift;
    return product < 0 ? (ap_int<32>)(-rounded) : (ap_int<32>)rounded;
}

static ap_int<32> scale_value(ap_int<32> value, ap_uint<16> multiplier,
                              ap_uint<8> shift)
{
#pragma HLS INLINE
    return round_shift((ap_int<64>)value * multiplier, shift);
}

static pose_q_data_t saturate_u8(ap_int<32> value)
{
#pragma HLS INLINE
    if (value < 0)
        return 0;
    if (value > 255)
        return 255;
    return (pose_q_data_t)value;
}

static pose_q_data_t requantize(pose_q_accum_t accum,
                                pose_q_word_t parameter,
                                int output_zero_point)
{
#pragma HLS INLINE
    ap_int<32> scaled = scale_value(accum, get_multiplier(parameter),
                                    get_shift(parameter));
    return saturate_u8(scaled + output_zero_point);
}

static void load_weight_cache(const pose_q_word_t *weights,
                              pose_q_weight_t cache[POSE_Q_MAX_CHANNELS]
                                                     [POSE_Q_MAX_CHANNELS],
                              int rows, int columns)
{
    pose_q_word_t packed[POSE_Q_MAX_WEIGHT_WORDS];
#pragma HLS ARRAY_PARTITION variable=cache cyclic factor=POSE_Q_PARALLEL_CHANNELS dim=1
    const int values = rows * columns;
    const int words = (values + 7) >> 3;
load_weight_words:
    for (int word = 0; word < words; ++word) {
#pragma HLS PIPELINE II=1
        packed[word] = weights[word];
    }
unpack_weight_rows:
    for (int row = 0; row < rows; ++row) {
    unpack_weight_columns:
        for (int column = 0; column < columns; ++column) {
#pragma HLS PIPELINE II=1
            int index = row * columns + column;
            cache[row][column] = get_weight(packed[index >> 3], index & 7);
        }
    }
}

static void load_depthwise_weight_cache(
    const pose_q_word_t *weights,
    pose_q_weight_t cache[POSE_Q_MAX_CHANNELS][9], int channels)
{
    pose_q_word_t packed[(POSE_Q_MAX_CHANNELS * 9 + 7) / 8];
#pragma HLS ARRAY_PARTITION variable=cache cyclic factor=POSE_Q_PARALLEL_CHANNELS dim=1
    const int values = channels * 9;
    const int words = (values + 7) >> 3;
load_dw_weight_words:
    for (int word = 0; word < words; ++word) {
#pragma HLS PIPELINE II=1
        packed[word] = weights[word];
    }
unpack_dw_channels:
    for (int channel = 0; channel < channels; ++channel) {
    unpack_dw_kernel:
        for (int kernel = 0; kernel < 9; ++kernel) {
#pragma HLS PIPELINE II=1
            int index = channel * 9 + kernel;
            cache[channel][kernel] = get_weight(packed[index >> 3], index & 7);
        }
    }
}

static void load_params(const pose_q_word_t *source,
                        pose_q_word_t cache[POSE_Q_MAX_CHANNELS], int channels)
{
#pragma HLS ARRAY_PARTITION variable=cache cyclic factor=POSE_Q_PARALLEL_CHANNELS dim=1
load_parameter_loop:
    for (int channel = 0; channel < channels; ++channel) {
#pragma HLS PIPELINE II=1
        cache[channel] = source[channel];
    }
}

static void store_channel_block(pose_q_word_t *output, int pixel,
                                int output_stride, int channel_base,
                                pose_q_data_t values[POSE_Q_PARALLEL_CHANNELS])
{
#pragma HLS INLINE
store_words:
    for (int word_lane = 0; word_lane < POSE_Q_WORDS_PER_BLOCK; ++word_lane) {
#pragma HLS PIPELINE II=1
        if (channel_base + word_lane * 8 < output_stride) {
            pose_q_word_t packed = 0;
        pack_word:
            for (int lane = 0; lane < 8; ++lane) {
#pragma HLS UNROLL
                packed.range(lane * 8 + 7, lane * 8) =
                    values[word_lane * 8 + lane];
            }
            output[((pixel * output_stride + channel_base) >> 3) + word_lane] =
                packed;
        }
    }
}

static void stem_conv(const pose_q_word_t *input_raw,
                      const pose_q_word_t *input_lut,
                      const pose_q_word_t *weights,
                      const pose_q_word_t *params, pose_q_word_t *output,
                      int height, int width, int output_channels, int stride,
                      int input_zero_point, int output_zero_point)
{
    pose_q_data_t raw_rows[3][POSE_Q_MAX_WIDTH * 3];
    pose_q_data_t quant_lut[256];
    pose_q_weight_t weight_cache[POSE_Q_MAX_CHANNELS][POSE_Q_MAX_CHANNELS];
    pose_q_word_t param_cache[POSE_Q_MAX_CHANNELS];
#pragma HLS ARRAY_PARTITION variable=raw_rows complete dim=1
#pragma HLS BIND_STORAGE variable=raw_rows type=ram_2p impl=bram
#pragma HLS ARRAY_PARTITION variable=weight_cache cyclic factor=POSE_Q_PARALLEL_CHANNELS dim=1
#pragma HLS ARRAY_PARTITION variable=param_cache cyclic factor=POSE_Q_PARALLEL_CHANNELS dim=1

load_lut_words:
    for (int word = 0; word < 32; ++word) {
#pragma HLS PIPELINE II=1
        pose_q_word_t packed = input_lut[word];
    load_lut_lanes:
        for (int lane = 0; lane < 8; ++lane) {
#pragma HLS UNROLL
            quant_lut[word * 8 + lane] = get_byte(packed, lane);
        }
    }
    load_weight_cache(weights, weight_cache, output_channels, 27);
    load_params(params, param_cache, output_channels);

    const int out_height = stride == 2 ? (height >> 1) : height;
    const int out_width = stride == 2 ? (width >> 1) : width;
    const int output_stride = (output_channels + 7) & ~7;
stem_y:
    for (int oy = 0; oy < out_height; ++oy) {
        stem_load_rows:
        for (int row_slot = 0; row_slot < 3; ++row_slot) {
            int iy = oy * stride + row_slot - 1;
        stem_load_row_words:
            for (int word = 0; word < (width * 3 >> 3); ++word) {
                pose_q_word_t packed = 0;
                if (iy >= 0 && iy < height)
                    packed = input_raw[iy * (width * 3 >> 3) + word];
            stem_unpack_row:
                for (int lane = 0; lane < 8; ++lane) {
#pragma HLS PIPELINE II=1
                    pose_q_data_t raw = get_byte(packed, lane);
                    raw_rows[row_slot][word * 8 + lane] = quant_lut[raw];
                }
            }
        }
    stem_x:
        for (int ox = 0; ox < out_width; ++ox) {
            pose_q_data_t patch[27];
#pragma HLS ARRAY_PARTITION variable=patch complete dim=1
        stem_patch_y:
            for (int ky = 0; ky < 3; ++ky) {
            stem_patch_x:
                for (int kx = 0; kx < 3; ++kx) {
                stem_patch_c:
                    for (int channel = 0; channel < 3; ++channel) {
#pragma HLS PIPELINE II=1
                        int iy = oy * stride + ky - 1;
                        int ix = ox * stride + kx - 1;
                        pose_q_data_t value = (pose_q_data_t)input_zero_point;
                        if (iy >= 0 && iy < height && ix >= 0 && ix < width) {
                            int index = ix * 3 + (2 - channel);
                            value = raw_rows[ky][index];
                        }
                        patch[(ky * 3 + kx) * 3 + channel] = value;
                    }
                }
            }
        stem_output_block:
            for (int channel_base = 0; channel_base < output_channels;
                 channel_base += POSE_Q_PARALLEL_CHANNELS) {
                pose_q_accum_t accum[POSE_Q_PARALLEL_CHANNELS];
                pose_q_data_t result[POSE_Q_PARALLEL_CHANNELS];
#pragma HLS ARRAY_PARTITION variable=accum complete dim=1
#pragma HLS ARRAY_PARTITION variable=result complete dim=1
            stem_init:
                for (int lane = 0; lane < POSE_Q_PARALLEL_CHANNELS; ++lane) {
#pragma HLS UNROLL
                    int channel = channel_base + lane;
                    accum[lane] = channel < output_channels
                                      ? get_bias(param_cache[channel])
                                      : pose_q_accum_t(0);
                }
            stem_mac:
                for (int kernel = 0; kernel < 27; ++kernel) {
#pragma HLS PIPELINE II=1
                stem_mac_lanes:
                    for (int lane = 0; lane < POSE_Q_PARALLEL_CHANNELS; ++lane) {
#pragma HLS UNROLL
                        int channel = channel_base + lane;
                        if (channel < output_channels)
                            accum[lane] +=
                                ((ap_int<9>)patch[kernel] - input_zero_point) *
                                weight_cache[channel][kernel];
                    }
                }
            stem_quantize:
                for (int lane = 0; lane < POSE_Q_PARALLEL_CHANNELS; ++lane) {
#pragma HLS PIPELINE II=1
                    int channel = channel_base + lane;
                    result[lane] = channel < output_channels
                                       ? requantize(accum[lane], param_cache[channel],
                                                    output_zero_point)
                                       : pose_q_data_t(0);
                }
                store_channel_block(output, oy * out_width + ox, output_stride,
                                    channel_base, result);
            }
        }
    }
}

static void depthwise_pointwise(
    const pose_q_word_t *input, const pose_q_word_t *dw_weights,
    const pose_q_word_t *dw_params, const pose_q_word_t *pw_weights,
    const pose_q_word_t *pw_params, pose_q_word_t *output, int height,
    int width, int input_channels, int output_channels, int stride,
    int input_zero_point, int dw_output_zero_point, int output_zero_point,
    int residual_zero_point, int residual_multiplier, int residual_shift,
    int residual_enable)
{
    pose_q_word_t feature_rows[3][POSE_Q_MAX_FEATURE_ROW_WORDS];
    pose_q_weight_t dw_weight_cache[POSE_Q_MAX_CHANNELS][9];
    pose_q_weight_t pw_weight_cache[POSE_Q_MAX_CHANNELS][POSE_Q_MAX_CHANNELS];
    pose_q_word_t dw_param_cache[POSE_Q_MAX_CHANNELS];
    pose_q_word_t pw_param_cache[POSE_Q_MAX_CHANNELS];
#pragma HLS ARRAY_PARTITION variable=feature_rows complete dim=1
#pragma HLS BIND_STORAGE variable=feature_rows type=ram_2p impl=bram
#pragma HLS ARRAY_PARTITION variable=dw_weight_cache cyclic factor=POSE_Q_PARALLEL_CHANNELS dim=1
#pragma HLS ARRAY_PARTITION variable=pw_weight_cache cyclic factor=POSE_Q_PARALLEL_CHANNELS dim=1
#pragma HLS ARRAY_PARTITION variable=pw_weight_cache cyclic factor=POSE_Q_INPUT_PARALLEL dim=2
#pragma HLS ARRAY_PARTITION variable=dw_param_cache cyclic factor=POSE_Q_PARALLEL_CHANNELS dim=1
#pragma HLS ARRAY_PARTITION variable=pw_param_cache cyclic factor=POSE_Q_PARALLEL_CHANNELS dim=1

    load_depthwise_weight_cache(dw_weights, dw_weight_cache, input_channels);
    load_params(dw_params, dw_param_cache, input_channels);
    load_weight_cache(pw_weights, pw_weight_cache, output_channels, input_channels);
    load_params(pw_params, pw_param_cache, output_channels);

    const int out_height = stride == 2 ? (height >> 1) : height;
    const int out_width = stride == 2 ? (width >> 1) : width;
    const int output_stride = (output_channels + 7) & ~7;
dw_pw_y:
    for (int oy = 0; oy < out_height; ++oy) {
    dw_pw_load_rows:
        for (int row_slot = 0; row_slot < 3; ++row_slot) {
            int iy = oy * stride + row_slot - 1;
        dw_pw_load_row_words:
            for (int word = 0; word < (width * input_channels >> 3); ++word) {
#pragma HLS PIPELINE II=1
                feature_rows[row_slot][word] =
                    (iy >= 0 && iy < height)
                        ? input[iy * (width * input_channels >> 3) + word]
                        : pose_q_word_t(0);
            }
        }
    dw_pw_x:
        for (int ox = 0; ox < out_width; ++ox) {
            pose_q_data_t dw_pixel[POSE_Q_MAX_CHANNELS];
#pragma HLS ARRAY_PARTITION variable=dw_pixel complete dim=1
        dw_channel_block:
            for (int channel_base = 0; channel_base < input_channels;
                 channel_base += POSE_Q_PARALLEL_CHANNELS) {
                pose_q_accum_t accum[POSE_Q_PARALLEL_CHANNELS];
#pragma HLS ARRAY_PARTITION variable=accum complete dim=1
            dw_init:
                for (int lane = 0; lane < POSE_Q_PARALLEL_CHANNELS; ++lane) {
#pragma HLS UNROLL
                    int channel = channel_base + lane;
                    accum[lane] = channel < input_channels
                                      ? get_bias(dw_param_cache[channel])
                                      : pose_q_accum_t(0);
                }
            dw_kernel_y:
                for (int ky = 0; ky < 3; ++ky) {
                dw_kernel_x:
                    for (int kx = 0; kx < 3; ++kx) {
#pragma HLS PIPELINE II=1
                        pose_q_word_t input_words[POSE_Q_WORDS_PER_BLOCK];
#pragma HLS ARRAY_PARTITION variable=input_words complete dim=1
                        int iy = oy * stride + ky - 1;
                        int ix = ox * stride + kx - 1;
                    dw_load_words:
                        for (int word_lane = 0;
                             word_lane < POSE_Q_WORDS_PER_BLOCK; ++word_lane) {
#pragma HLS UNROLL
                            int first_channel = channel_base + word_lane * 8;
                            if (iy >= 0 && iy < height && ix >= 0 && ix < width &&
                                first_channel < input_channels) {
                                int word_index =
                                    (ix * input_channels + first_channel) >> 3;
                                input_words[word_lane] =
                                    feature_rows[ky][word_index];
                            } else {
                                input_words[word_lane] = 0;
                            }
                        }
                    dw_mac_lanes:
                        for (int lane = 0; lane < POSE_Q_PARALLEL_CHANNELS; ++lane) {
#pragma HLS UNROLL
                            int channel = channel_base + lane;
                            if (channel < input_channels && iy >= 0 && iy < height &&
                                ix >= 0 && ix < width) {
                                pose_q_data_t value =
                                    get_byte(input_words[lane >> 3], lane & 7);
                                accum[lane] +=
                                    ((ap_int<9>)value - input_zero_point) *
                                    dw_weight_cache[channel][ky * 3 + kx];
                            }
                        }
                    }
                }
            dw_quantize:
                for (int lane = 0; lane < POSE_Q_PARALLEL_CHANNELS; ++lane) {
#pragma HLS PIPELINE II=1
                    int channel = channel_base + lane;
                    if (channel < input_channels)
                        dw_pixel[channel] =
                            requantize(accum[lane], dw_param_cache[channel],
                                       dw_output_zero_point);
                }
            }

        pw_output_block:
            for (int channel_base = 0; channel_base < output_channels;
                 channel_base += POSE_Q_PARALLEL_CHANNELS) {
                pose_q_accum_t accum[POSE_Q_PARALLEL_CHANNELS];
                pose_q_accum_t accum_odd[POSE_Q_PARALLEL_CHANNELS];
                pose_q_data_t result[POSE_Q_PARALLEL_CHANNELS];
#pragma HLS ARRAY_PARTITION variable=accum complete dim=1
#pragma HLS ARRAY_PARTITION variable=accum_odd complete dim=1
#pragma HLS ARRAY_PARTITION variable=result complete dim=1
            pw_init:
                for (int lane = 0; lane < POSE_Q_PARALLEL_CHANNELS; ++lane) {
#pragma HLS UNROLL
                    int channel = channel_base + lane;
                    accum[lane] = channel < output_channels
                                      ? get_bias(pw_param_cache[channel])
                                      : pose_q_accum_t(0);
                    accum_odd[lane] = 0;
                }
            pw_mac:
                for (int input_channel = 0; input_channel < input_channels;
                     input_channel += POSE_Q_INPUT_PARALLEL) {
#pragma HLS PIPELINE II=1
                pw_mac_lanes:
                    for (int lane = 0; lane < POSE_Q_PARALLEL_CHANNELS; ++lane) {
#pragma HLS UNROLL
                        int channel = channel_base + lane;
                        if (channel < output_channels) {
                            accum[lane] +=
                                ((ap_int<9>)dw_pixel[input_channel] -
                                 dw_output_zero_point) *
                                pw_weight_cache[channel][input_channel];
                            if (input_channel + 1 < input_channels)
                                accum_odd[lane] +=
                                    ((ap_int<9>)dw_pixel[input_channel + 1] -
                                     dw_output_zero_point) *
                                    pw_weight_cache[channel][input_channel + 1];
                        }
                    }
                }
            pw_quantize:
                pose_q_word_t residual_words[POSE_Q_WORDS_PER_BLOCK];
#pragma HLS ARRAY_PARTITION variable=residual_words complete dim=1
            load_residual_words:
                for (int word_lane = 0;
                     word_lane < POSE_Q_WORDS_PER_BLOCK; ++word_lane) {
#pragma HLS PIPELINE II=1
                    int first_channel = channel_base + word_lane * 8;
                    if (residual_enable && first_channel < input_channels) {
                        int word_index =
                            (ox * input_channels + first_channel) >> 3;
                        residual_words[word_lane] =
                            feature_rows[1][word_index];
                    } else {
                        residual_words[word_lane] = 0;
                    }
                }
                for (int lane = 0; lane < POSE_Q_PARALLEL_CHANNELS; ++lane) {
#pragma HLS PIPELINE II=1
                    int channel = channel_base + lane;
                    ap_int<32> value = 0;
                    if (channel < output_channels) {
                        pose_q_accum_t relu_accum = accum[lane] + accum_odd[lane];
                        if (relu_accum < 0)
                            relu_accum = 0;
                        value = scale_value(relu_accum,
                                            get_multiplier(pw_param_cache[channel]),
                                            get_shift(pw_param_cache[channel]));
                        if (residual_enable) {
                            pose_q_data_t residual_value =
                                get_byte(residual_words[lane >> 3], lane & 7);
                            value += scale_value(
                                (ap_int<32>)residual_value - residual_zero_point,
                                (ap_uint<16>)residual_multiplier,
                                (ap_uint<8>)residual_shift);
                        }
                        value += output_zero_point;
                    }
                    result[lane] = channel < output_channels
                                       ? saturate_u8(value)
                                       : pose_q_data_t(0);
                }
                store_channel_block(output, oy * out_width + ox, output_stride,
                                    channel_base, result);
            }
        }
    }
}

static void pointwise_conv(
    const pose_q_word_t *input, const pose_q_word_t *weights,
    const pose_q_word_t *params, const pose_q_word_t *residual,
    pose_q_word_t *output, int height, int width, int input_channels,
    int output_channels, int input_zero_point, int output_zero_point,
    int residual_zero_point, int residual_multiplier, int residual_shift,
    int relu_enable, int residual_enable)
{
    pose_q_weight_t weight_cache[POSE_Q_MAX_CHANNELS][POSE_Q_MAX_CHANNELS];
    pose_q_word_t param_cache[POSE_Q_MAX_CHANNELS];
#pragma HLS ARRAY_PARTITION variable=weight_cache cyclic factor=POSE_Q_PARALLEL_CHANNELS dim=1
#pragma HLS ARRAY_PARTITION variable=weight_cache cyclic factor=POSE_Q_INPUT_PARALLEL dim=2
#pragma HLS ARRAY_PARTITION variable=param_cache cyclic factor=POSE_Q_PARALLEL_CHANNELS dim=1
    load_weight_cache(weights, weight_cache, output_channels, input_channels);
    load_params(params, param_cache, output_channels);
    const int pixels = height * width;
    const int output_stride = (output_channels + 7) & ~7;
pw_pixel:
    for (int pixel = 0; pixel < pixels; ++pixel) {
        pose_q_data_t input_pixel[POSE_Q_MAX_CHANNELS];
#pragma HLS ARRAY_PARTITION variable=input_pixel complete dim=1
    pw_load_words:
        for (int word = 0; word < (input_channels >> 3); ++word) {
#pragma HLS PIPELINE II=1
            pose_q_word_t packed = input[((pixel * input_channels) >> 3) + word];
        pw_unpack_input:
            for (int lane = 0; lane < 8; ++lane) {
#pragma HLS UNROLL
                input_pixel[word * 8 + lane] = get_byte(packed, lane);
            }
        }
    pw_output_block:
        for (int channel_base = 0; channel_base < output_channels;
             channel_base += POSE_Q_PARALLEL_CHANNELS) {
            pose_q_accum_t accum[POSE_Q_PARALLEL_CHANNELS];
            pose_q_accum_t accum_odd[POSE_Q_PARALLEL_CHANNELS];
            pose_q_data_t result[POSE_Q_PARALLEL_CHANNELS];
#pragma HLS ARRAY_PARTITION variable=accum complete dim=1
#pragma HLS ARRAY_PARTITION variable=accum_odd complete dim=1
#pragma HLS ARRAY_PARTITION variable=result complete dim=1
        pw_init:
            for (int lane = 0; lane < POSE_Q_PARALLEL_CHANNELS; ++lane) {
#pragma HLS UNROLL
                int channel = channel_base + lane;
                accum[lane] = channel < output_channels
                                  ? get_bias(param_cache[channel])
                                  : pose_q_accum_t(0);
                accum_odd[lane] = 0;
            }
        pw_mac:
            for (int input_channel = 0; input_channel < input_channels;
                 input_channel += POSE_Q_INPUT_PARALLEL) {
#pragma HLS PIPELINE II=1
            pw_mac_lanes:
                for (int lane = 0; lane < POSE_Q_PARALLEL_CHANNELS; ++lane) {
#pragma HLS UNROLL
                    int channel = channel_base + lane;
                    if (channel < output_channels) {
                        accum[lane] +=
                            ((ap_int<9>)input_pixel[input_channel] - input_zero_point) *
                            weight_cache[channel][input_channel];
                        if (input_channel + 1 < input_channels)
                            accum_odd[lane] +=
                                ((ap_int<9>)input_pixel[input_channel + 1] -
                                 input_zero_point) *
                                weight_cache[channel][input_channel + 1];
                    }
                }
            }
        pw_quantize:
            for (int lane = 0; lane < POSE_Q_PARALLEL_CHANNELS; ++lane) {
#pragma HLS PIPELINE II=1
                int channel = channel_base + lane;
                ap_int<32> value = 0;
                if (channel < output_channels) {
                    pose_q_accum_t active_accum = accum[lane] + accum_odd[lane];
                    if (relu_enable && active_accum < 0)
                        active_accum = 0;
                    value = scale_value(active_accum,
                                        get_multiplier(param_cache[channel]),
                                        get_shift(param_cache[channel]));
                    if (residual_enable) {
                        int residual_index = pixel * output_stride + channel;
                        pose_q_word_t packed = residual[residual_index >> 3];
                        pose_q_data_t residual_value =
                            get_byte(packed, residual_index & 7);
                        value += scale_value(
                            (ap_int<32>)residual_value - residual_zero_point,
                            (ap_uint<16>)residual_multiplier,
                            (ap_uint<8>)residual_shift);
                    }
                    value += output_zero_point;
                }
                result[lane] = channel < output_channels
                                   ? saturate_u8(value)
                                   : pose_q_data_t(0);
            }
            store_channel_block(output, pixel, output_stride, channel_base,
                                result);
        }
    }
}

static void upsample_add(
    const pose_q_word_t *input, const pose_q_word_t *input_params,
    const pose_q_word_t *residual, pose_q_word_t *output, int height,
    int width, int channels, int input_zero_point, int output_zero_point,
    int residual_zero_point, int residual_multiplier, int residual_shift)
{
    pose_q_word_t input_parameter = input_params[0];
    ap_uint<16> input_multiplier = get_multiplier(input_parameter);
    ap_uint<8> input_shift = get_shift(input_parameter);
    const int out_height = height << 1;
    const int out_width = width << 1;
upsample_y:
    for (int y = 0; y < out_height; ++y) {
    upsample_x:
        for (int x = 0; x < out_width; ++x) {
        upsample_channel_block:
            for (int channel_base = 0; channel_base < channels;
                 channel_base += POSE_Q_PARALLEL_CHANNELS) {
                pose_q_data_t result[POSE_Q_PARALLEL_CHANNELS];
#pragma HLS ARRAY_PARTITION variable=result complete dim=1
            upsample_word:
                for (int word_lane = 0;
                     word_lane < POSE_Q_WORDS_PER_BLOCK; ++word_lane) {
                    int source_index =
                        (((y >> 1) * width + (x >> 1)) * channels +
                         channel_base + word_lane * 8) >> 3;
                    int residual_index =
                        ((y * out_width + x) * channels + channel_base +
                         word_lane * 8) >> 3;
                    pose_q_word_t source_word = input[source_index];
                    pose_q_word_t residual_word = residual[residual_index];
                upsample_lanes:
                    for (int lane = 0; lane < 8; ++lane) {
#pragma HLS PIPELINE II=1
                        int result_lane = word_lane * 8 + lane;
                        ap_int<32> source_value =
                            (ap_int<32>)get_byte(source_word, lane) - input_zero_point;
                        ap_int<32> residual_value =
                            (ap_int<32>)get_byte(residual_word, lane) -
                            residual_zero_point;
                        result[result_lane] = saturate_u8(
                            scale_value(source_value, input_multiplier, input_shift) +
                            scale_value(residual_value,
                                        (ap_uint<16>)residual_multiplier,
                                        (ap_uint<8>)residual_shift) +
                            output_zero_point);
                    }
                }
                store_channel_block(output, y * out_width + x, channels,
                                    channel_base, result);
            }
        }
    }
}

void pose_cnn_accel(
    const pose_q_word_t *input_raw, const pose_q_word_t *input,
    const pose_q_word_t *input_lut, const pose_q_word_t *dw_weights,
    const pose_q_word_t *dw_params, const pose_q_word_t *pw_weights,
    const pose_q_word_t *pw_params, const pose_q_word_t *residual,
    pose_q_word_t *output, int operation, int height, int width,
    int input_channels, int output_channels, int stride,
    int input_zero_point, int dw_output_zero_point, int output_zero_point,
    int residual_zero_point, int residual_multiplier, int residual_shift,
    int relu_enable, int residual_enable)
{
#pragma HLS INTERFACE m_axi port=input_raw offset=slave bundle=gmem0 depth=13824 max_read_burst_length=64 num_read_outstanding=16
#pragma HLS INTERFACE m_axi port=input offset=slave bundle=gmem0 depth=27648 max_read_burst_length=64 num_read_outstanding=16
#pragma HLS INTERFACE m_axi port=residual offset=slave bundle=gmem1 depth=27648 max_read_burst_length=64 num_read_outstanding=16
#pragma HLS INTERFACE m_axi port=input_lut offset=slave bundle=gmem1 depth=32 max_read_burst_length=64 num_read_outstanding=16
#pragma HLS INTERFACE m_axi port=dw_weights offset=slave bundle=gmem1 depth=288 max_read_burst_length=64 num_read_outstanding=16
#pragma HLS INTERFACE m_axi port=dw_params offset=slave bundle=gmem1 depth=48 max_read_burst_length=64 num_read_outstanding=16
#pragma HLS INTERFACE m_axi port=pw_weights offset=slave bundle=gmem1 depth=288 max_read_burst_length=64 num_read_outstanding=16
#pragma HLS INTERFACE m_axi port=pw_params offset=slave bundle=gmem1 depth=48 max_read_burst_length=64 num_read_outstanding=16
#pragma HLS INTERFACE m_axi port=output offset=slave bundle=gmem2 depth=27648 max_write_burst_length=64 num_write_outstanding=16
#pragma HLS INTERFACE s_axilite port=input_raw bundle=control
#pragma HLS INTERFACE s_axilite port=input bundle=control
#pragma HLS INTERFACE s_axilite port=input_lut bundle=control
#pragma HLS INTERFACE s_axilite port=dw_weights bundle=control
#pragma HLS INTERFACE s_axilite port=dw_params bundle=control
#pragma HLS INTERFACE s_axilite port=pw_weights bundle=control
#pragma HLS INTERFACE s_axilite port=pw_params bundle=control
#pragma HLS INTERFACE s_axilite port=residual bundle=control
#pragma HLS INTERFACE s_axilite port=output bundle=control
#pragma HLS INTERFACE s_axilite port=operation bundle=control
#pragma HLS INTERFACE s_axilite port=height bundle=control
#pragma HLS INTERFACE s_axilite port=width bundle=control
#pragma HLS INTERFACE s_axilite port=input_channels bundle=control
#pragma HLS INTERFACE s_axilite port=output_channels bundle=control
#pragma HLS INTERFACE s_axilite port=stride bundle=control
#pragma HLS INTERFACE s_axilite port=input_zero_point bundle=control
#pragma HLS INTERFACE s_axilite port=dw_output_zero_point bundle=control
#pragma HLS INTERFACE s_axilite port=output_zero_point bundle=control
#pragma HLS INTERFACE s_axilite port=residual_zero_point bundle=control
#pragma HLS INTERFACE s_axilite port=residual_multiplier bundle=control
#pragma HLS INTERFACE s_axilite port=residual_shift bundle=control
#pragma HLS INTERFACE s_axilite port=relu_enable bundle=control
#pragma HLS INTERFACE s_axilite port=residual_enable bundle=control
#pragma HLS INTERFACE s_axilite port=return bundle=control

    if (height <= 0 || height > POSE_Q_MAX_HEIGHT || width <= 0 ||
        width > POSE_Q_MAX_WIDTH || input_channels <= 0 ||
        input_channels > POSE_Q_MAX_CHANNELS || output_channels <= 0 ||
        output_channels > POSE_Q_MAX_CHANNELS || (stride != 1 && stride != 2))
        return;

    if (operation == POSE_CNN_STEM && input_channels == 3)
        stem_conv(input_raw, input_lut, pw_weights, pw_params, output, height,
                  width, output_channels, stride, input_zero_point,
                  output_zero_point);
    else if (operation == POSE_CNN_DW_PW && (input_channels & 7) == 0)
        depthwise_pointwise(
            input, dw_weights, dw_params, pw_weights, pw_params, output,
            height, width, input_channels, output_channels, stride,
            input_zero_point, dw_output_zero_point, output_zero_point,
            residual_zero_point, residual_multiplier, residual_shift,
            residual_enable);
    else if (operation == POSE_CNN_POINTWISE && (input_channels & 7) == 0)
        pointwise_conv(input, pw_weights, pw_params, residual, output, height,
                       width, input_channels, output_channels, input_zero_point,
                       output_zero_point, residual_zero_point,
                       residual_multiplier, residual_shift, relu_enable,
                       residual_enable);
    else if (operation == POSE_CNN_UPSAMPLE_ADD &&
             input_channels == output_channels && (input_channels & 7) == 0)
        upsample_add(input, dw_params, residual, output, height, width,
                     input_channels, input_zero_point, output_zero_point,
                     residual_zero_point, residual_multiplier, residual_shift);
}
