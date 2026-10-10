#ifndef POSE_CNN_ACCEL_H
#define POSE_CNN_ACCEL_H

#include <ap_int.h>

static const int POSE_Q_MAX_HEIGHT = 144;
static const int POSE_Q_MAX_WIDTH = 256;
static const int POSE_Q_MAX_CHANNELS = 48;
/* Sixteen output channels and two input channels are evaluated per MAC step. */
static const int POSE_Q_PARALLEL_CHANNELS = 16;
static const int POSE_Q_INPUT_PARALLEL = 2;
static const int POSE_Q_WORDS_PER_BLOCK = POSE_Q_PARALLEL_CHANNELS / 8;
static const int POSE_Q_MAX_RAW_WORDS = (144 * 256 * 3) / 8;
static const int POSE_Q_MAX_FEATURE_WORDS = (72 * 128 * 24) / 8;
static const int POSE_Q_MAX_WEIGHT_WORDS = (48 * 48) / 8;
static const int POSE_Q_MAX_RAW_ROW_WORDS = (256 * 3) / 8;
/* The widest real feature row is 128 x 24 bytes. */
static const int POSE_Q_MAX_FEATURE_ROW_WORDS = (128 * 24) / 8;

typedef ap_uint<64> pose_q_word_t;
typedef ap_uint<8> pose_q_data_t;
typedef ap_int<8> pose_q_weight_t;
typedef ap_int<32> pose_q_accum_t;

enum PoseCnnOperation {
    POSE_CNN_STEM = 0,
    POSE_CNN_DW_PW = 1,
    POSE_CNN_POINTWISE = 2,
    POSE_CNN_UPSAMPLE_ADD = 3
};

void pose_cnn_accel(
    const pose_q_word_t *input_raw,
    const pose_q_word_t *input,
    const pose_q_word_t *input_lut,
    const pose_q_word_t *dw_weights,
    const pose_q_word_t *dw_params,
    const pose_q_word_t *pw_weights,
    const pose_q_word_t *pw_params,
    const pose_q_word_t *residual,
    pose_q_word_t *output,
    int operation,
    int height,
    int width,
    int input_channels,
    int output_channels,
    int stride,
    int input_zero_point,
    int dw_output_zero_point,
    int output_zero_point,
    int residual_zero_point,
    int residual_multiplier,
    int residual_shift,
    int relu_enable,
    int residual_enable);

#endif
