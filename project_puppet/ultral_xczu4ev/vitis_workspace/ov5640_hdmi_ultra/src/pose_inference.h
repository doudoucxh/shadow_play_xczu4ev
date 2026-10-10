/* Bare-metal reference inference for the trained TinyUpperPoseNet. */
#ifndef POSE_INFERENCE_H
#define POSE_INFERENCE_H

#include "xaxivdma.h"
#include "xil_cache.h"
#include "xil_io.h"
#include "xil_printf.h"
#include "xtime_l.h"
#include "sleep.h"
#include <string.h>
#include "pose_model_weights.h"
#include "pose_model_int8_weights.h"

#ifndef POSE_MODEL_ARCH
#define POSE_MODEL_ARCH 1
#define POSE_STEM_CHANNELS 16U
#define POSE_HIGH_CHANNELS 24U
#define POSE_LOW_CHANNELS 32U
#endif

#define POSE_INPUT_WIDTH 256U
#define POSE_INPUT_HEIGHT 144U
#define POSE_INPUT_BYTES (POSE_INPUT_WIDTH * POSE_INPUT_HEIGHT * 3U)
#define POSE_HEATMAP_WIDTH 64U
#define POSE_HEATMAP_HEIGHT 36U
#define POSE_KEYPOINTS 9U
#define POSE_RESULT_ADDR 0x02200000U
#define POSE_RESULT_MAGIC 0x504F5345U
#define POSE_LOGIT_THRESHOLD_MILLI (-2442)
#define VIDEO_WIDTH 1280U
#define VIDEO_HEIGHT 720U
#define VIDEO_FRAME_BYTES (VIDEO_WIDTH * VIDEO_HEIGHT * 3U)
#define VIDEO_DISPLAY_BASE 0x01800000U
#define VIDEO_SNAPSHOT_ADDR 0x01E00000U
#define POSE_DEBUG_INPUT_ADDR 0x02300000U
#define POSE_DEBUG_HEATMAP_ADDR 0x02400000U
#define POSE_SNAPSHOT_INTERVAL 30U
#define POSE_RESULT_VERSION 7U
#define POSE_RESULT_BYTES 224U
#define POSE_GRID_WIDTH 32U
#define POSE_GRID_HEIGHT 18U
#define POSE_GRID_CELLS (POSE_GRID_WIDTH * POSE_GRID_HEIGHT)

#define POSE_MAX_FEATURE (128U * 72U * POSE_STEM_CHANNELS)
#define POSE_HIGH_FEATURE (64U * 36U * POSE_HIGH_CHANNELS)
#define POSE_LOW_FEATURE (32U * 18U * POSE_LOW_CHANNELS)
#define POSE_HEATMAP_FEATURE (POSE_HEATMAP_WIDTH * POSE_HEATMAP_HEIGHT * POSE_KEYPOINTS)
#define POSE_Q_HEATMAP_STRIDE 16U
#define POSE_Q_HEATMAP_FEATURE (POSE_HEATMAP_WIDTH * POSE_HEATMAP_HEIGHT * POSE_Q_HEATMAP_STRIDE)
#define POSE_CNN_STATUS_ADDR 0x02200100U
#define POSE_CNN_STATUS_MAGIC 0x434E4E50U

#ifndef XPAR_POSE_CNN_ACCEL_0_S_AXI_CONTROL_BASEADDR
#define XPAR_POSE_CNN_ACCEL_0_S_AXI_CONTROL_BASEADDR 0x43C00000U
#endif

#define POSE_CNN_REG_CONTROL 0x00U
#define POSE_CNN_REG_INPUT_RAW 0x10U
#define POSE_CNN_REG_INPUT 0x1CU
#define POSE_CNN_REG_INPUT_LUT 0x28U
#define POSE_CNN_REG_DW_WEIGHTS 0x34U
#define POSE_CNN_REG_DW_PARAMS 0x40U
#define POSE_CNN_REG_PW_WEIGHTS 0x4CU
#define POSE_CNN_REG_PW_PARAMS 0x58U
#define POSE_CNN_REG_RESIDUAL 0x64U
#define POSE_CNN_REG_OUTPUT 0x70U
#define POSE_CNN_REG_OPERATION 0x7CU
#define POSE_CNN_REG_HEIGHT 0x84U
#define POSE_CNN_REG_WIDTH 0x8CU
#define POSE_CNN_REG_INPUT_CHANNELS 0x94U
#define POSE_CNN_REG_OUTPUT_CHANNELS 0x9CU
#define POSE_CNN_REG_STRIDE 0xA4U
#define POSE_CNN_REG_INPUT_ZP 0xACU
#define POSE_CNN_REG_DW_OUTPUT_ZP 0xB4U
#define POSE_CNN_REG_OUTPUT_ZP 0xBCU
#define POSE_CNN_REG_RESIDUAL_ZP 0xC4U
#define POSE_CNN_REG_RESIDUAL_MULT 0xCCU
#define POSE_CNN_REG_RESIDUAL_SHIFT 0xD4U
#define POSE_CNN_REG_RELU_ENABLE 0xDCU
#define POSE_CNN_REG_RESIDUAL_ENABLE 0xE4U

#define POSE_CNN_OP_STEM 0U
#define POSE_CNN_OP_DEPTHWISE 1U
#define POSE_CNN_OP_POINTWISE 2U
#define POSE_CNN_OP_UPSAMPLE_ADD 3U

typedef struct {
    s32 x;
    s32 y;
    s32 logit_milli;
} PosePoint;

typedef struct {
    s32 x;
    s32 y;
    s32 width;
    s32 height;
    u32 motion_pixels;
    u32 initialized;
} PoseRoi;

/* The visible subject is already an upper body.  The yellow rectangle is the
 * exact 16:9 subject ROI consumed by the keypoint network. */
typedef struct {
    s32 x;
    s32 y;
    s32 width;
    s32 height;
    u32 motion_pixels;
    u32 initialized;
} PersonRoi;

typedef struct {
    u32 magic;
    u32 version;
    u32 struct_bytes;
    u32 snapshot_sequence;
    u32 model_sha256[8];
    u32 frame_counter;
    u32 input_frame_index;
    u32 elapsed_us;
    u32 backend_pl;
    u32 completed_layers;
    u32 failed_layer;
    u32 inference_us;
    u32 input_address;
    u32 input_bytes;
    u32 heatmap_address;
    u32 heatmap_bytes;
    s32 roi_x;
    s32 roi_y;
    s32 roi_width;
    s32 roi_height;
    u32 motion_pixels;
    PosePoint points[POSE_KEYPOINTS];
    u32 snapshot_sequence_end;
} PoseHardwareResult;

typedef char PoseHardwareResult_size_must_be_224_bytes[
    sizeof(PoseHardwareResult) == POSE_RESULT_BYTES ? 1 : -1];

static float pose_feature0[POSE_MAX_FEATURE] POSE_ALIGN;
static float pose_feature1[POSE_MAX_FEATURE] POSE_ALIGN;
static float pose_high[POSE_HIGH_FEATURE] POSE_ALIGN;
static float pose_low_extra[POSE_LOW_FEATURE] POSE_ALIGN;
static float pose_input_lut[256] POSE_ALIGN;
static u8 pose_q_feature0[POSE_MAX_FEATURE] POSE_Q_ALIGN;
static u8 pose_q_feature1[POSE_MAX_FEATURE] POSE_Q_ALIGN;
static u8 pose_q_high[POSE_HIGH_FEATURE] POSE_Q_ALIGN;
static u8 pose_q_low_extra[POSE_LOW_FEATURE] POSE_Q_ALIGN;
static u8 pose_q_heatmaps[POSE_Q_HEATMAP_FEATURE] POSE_Q_ALIGN;
static u8 pose_model_input[POSE_INPUT_BYTES] POSE_ALIGN;
static u8 pose_previous_gray[POSE_INPUT_WIDTH * POSE_INPUT_HEIGHT] POSE_ALIGN;
static u8 pose_motion_cells[POSE_GRID_CELLS] POSE_ALIGN;
static u8 pose_motion_history[POSE_GRID_CELLS] POSE_ALIGN;
static u8 pose_visited_cells[POSE_GRID_CELLS] POSE_ALIGN;
static u16 pose_component_queue[POSE_GRID_CELLS] POSE_ALIGN;
static PosePoint pose_current_points[POSE_KEYPOINTS] POSE_ALIGN;
static PosePoint pose_display_points[POSE_KEYPOINTS] POSE_ALIGN;
static PosePoint pose_pending_points[POSE_KEYPOINTS] POSE_ALIGN;
static u8 pose_pending_valid[POSE_KEYPOINTS] POSE_ALIGN;

typedef struct {
    u32 magic;
    u32 version;
    u32 backend_pl;
    u32 completed_layers;
    u32 failed_layer;
    u32 inference_us;
} PoseCnnHardwareStatus;

#ifndef POSE_VALIDATION_BUILD
#define POSE_VALIDATION_BUILD 1
#endif
static u32 pose_display_ready;
static u32 pose_display_buffer_index;

static s32 pose_abs_s32(s32 value);

static float pose_relu(float value)
{
    return value > 0.0f ? value : 0.0f;
}

static void pose_make_input_lut(void)
{
    u32 index;
    for (index = 0; index < 256U; ++index)
        pose_input_lut[index] = (float)index * (1.0f / 127.5f) - 1.0f;
}

static s32 pose_clamp_s32(s32 value, s32 minimum, s32 maximum)
{
    if (value < minimum)
        return minimum;
    if (value > maximum)
        return maximum;
    return value;
}

static u8 pose_gray_pixel(const u8 *pixel)
{
    return (u8)(((u32)pixel[0] + ((u32)pixel[1] << 1) + (u32)pixel[2]) >> 2);
}

/*
 * Motion is accumulated on an 8x8 grid.  Connected components are scored
 * against the previous ROI so that a larger moving person at the side does
 * not immediately steal the target.  The first ROI is centred on screen.
 */
static void pose_update_roi(const u8 *frame, PoseRoi *roi)
{
    u32 y, x;
    s32 best_score = -2147483647;
    s32 best_left = 0, best_top = 0, best_right = 0, best_bottom = 0;
    u32 best_motion = 0U, best_weight_x = 0U, best_weight_y = 0U;

    memset(pose_motion_cells, 0, sizeof(pose_motion_cells));
    memset(pose_visited_cells, 0, sizeof(pose_visited_cells));
    for (y = 0; y < POSE_INPUT_HEIGHT; ++y) {
        for (x = 0; x < POSE_INPUT_WIDTH; ++x) {
            u32 pixel_index = y * POSE_INPUT_WIDTH + x;
            u8 gray = pose_gray_pixel(frame + pixel_index * 3U);
            if (roi->initialized) {
                s32 delta = (s32)gray - (s32)pose_previous_gray[pixel_index];
                u32 cell;
                if (delta < 0)
                    delta = -delta;
                cell = (y >> 3) * POSE_GRID_WIDTH + (x >> 3);
                if (delta > 28 && pose_motion_cells[cell] < 255U)
                    ++pose_motion_cells[cell];
            }
            pose_previous_gray[pixel_index] = gray;
        }
    }

    if (!roi->initialized) {
        roi->x = 48;
        roi->y = 27;
        roi->width = 160;
        roi->height = 90;
        roi->motion_pixels = 0U;
        roi->initialized = 1U;
        return;
    }

    for (y = 0; y < POSE_GRID_HEIGHT; ++y) {
        for (x = 0; x < POSE_GRID_WIDTH; ++x) {
            u32 start = y * POSE_GRID_WIDTH + x;
            u32 head = 0U, tail = 0U;
            u32 motion = 0U, weighted_x = 0U, weighted_y = 0U;
            s32 left = (s32)x, right = (s32)x;
            s32 top = (s32)y, bottom = (s32)y;
            s32 center_x, center_y, prior_x, prior_y, distance2, score;
            if (pose_visited_cells[start] || pose_motion_cells[start] < 8U)
                continue;
            pose_visited_cells[start] = 1U;
            pose_component_queue[tail++] = (u16)start;
            while (head < tail) {
                u32 cell = pose_component_queue[head++];
                s32 cell_x = (s32)(cell % POSE_GRID_WIDTH);
                s32 cell_y = (s32)(cell / POSE_GRID_WIDTH);
                u32 count = pose_motion_cells[cell];
                static const s8 offset_x[4] = {-1, 1, 0, 0};
                static const s8 offset_y[4] = {0, 0, -1, 1};
                u32 neighbor;
                motion += count;
                weighted_x += count * (u32)(cell_x * 8 + 4);
                weighted_y += count * (u32)(cell_y * 8 + 4);
                if (cell_x < left) left = cell_x;
                if (cell_x > right) right = cell_x;
                if (cell_y < top) top = cell_y;
                if (cell_y > bottom) bottom = cell_y;
                for (neighbor = 0; neighbor < 4U; ++neighbor) {
                    s32 nx = cell_x + offset_x[neighbor];
                    s32 ny = cell_y + offset_y[neighbor];
                    u32 next;
                    if (nx < 0 || ny < 0 || nx >= (s32)POSE_GRID_WIDTH ||
                        ny >= (s32)POSE_GRID_HEIGHT)
                        continue;
                    next = (u32)ny * POSE_GRID_WIDTH + (u32)nx;
                    if (!pose_visited_cells[next] && pose_motion_cells[next] >= 8U) {
                        pose_visited_cells[next] = 1U;
                        pose_component_queue[tail++] = (u16)next;
                    }
                }
            }
            if (motion < 40U)
                continue;
            center_x = (s32)(weighted_x / motion);
            center_y = (s32)(weighted_y / motion);
            prior_x = roi->x + roi->width / 2;
            prior_y = roi->y + roi->height / 2;
            if (center_x < roi->x - 24 || center_x >= roi->x + roi->width + 24 ||
                center_y < roi->y - 16 || center_y >= roi->y + roi->height + 16)
                continue;
            distance2 = (center_x - prior_x) * (center_x - prior_x) +
                        (center_y - prior_y) * (center_y - prior_y);
            score = (s32)(motion * 48U) - distance2 * 4;
            if (center_x >= roi->x && center_x < roi->x + roi->width &&
                center_y >= roi->y && center_y < roi->y + roi->height)
                score += 5000;
            if (score > best_score) {
                best_score = score;
                best_left = left;
                best_right = right;
                best_top = top;
                best_bottom = bottom;
                best_motion = motion;
                best_weight_x = weighted_x;
                best_weight_y = weighted_y;
            }
        }
    }

    if (best_motion != 0U) {
        s32 box_top = best_top * 8;
        s32 box_height = (best_bottom - best_top + 1) * 8;
        s32 target_center_x = (s32)(best_weight_x / best_motion);
        s32 box_width = (best_right - best_left + 1) * 8;
        s32 target_height = pose_clamp_s32(box_height + 32, 72, 99);
        s32 target_width = pose_clamp_s32((target_height * 16) / 9, 128, 176);
        s32 target_center_y;
        s32 new_center_x, new_center_y, new_width, new_height;
        target_height = (target_width * 9) / 16;
        /* Keep the upper body in view when the moving component spans a person. */
        target_center_y = box_top + target_height / 2 - 6;
        if (box_height < 32)
            target_center_y = (s32)(best_weight_y / best_motion);
        if (box_width < 32 && box_height < 40) {
            target_center_x = roi->x + roi->width / 2;
            target_center_y = roi->y + roi->height / 2;
        }
        target_center_x = pose_clamp_s32(target_center_x,
                                         roi->x + roi->width / 2 - 12,
                                         roi->x + roi->width / 2 + 12);
        target_center_y = pose_clamp_s32(target_center_y,
                                         roi->y + roi->height / 2 - 8,
                                         roi->y + roi->height / 2 + 8);
        new_center_x = (roi->x + roi->width / 2) * 3 / 4 + target_center_x / 4;
        new_center_y = (roi->y + roi->height / 2) * 3 / 4 + target_center_y / 4;
        new_width = (roi->width * 7 + target_width) / 8;
        new_width = pose_clamp_s32(new_width, 128, 176);
        new_height = (new_width * 9) / 16;
        roi->x = pose_clamp_s32(new_center_x - new_width / 2, 0,
                                (s32)POSE_INPUT_WIDTH - new_width);
        roi->y = pose_clamp_s32(new_center_y - new_height / 2, 0,
                                (s32)POSE_INPUT_HEIGHT - new_height);
        roi->width = new_width;
        roi->height = new_height;
        roi->motion_pixels = best_motion;
    } else {
        roi->motion_pixels = 0U;
    }
}

/* Track the central visible upper body.  Motion only nudges a persistent
 * 16:9 window; the window is kept large enough for both raised arms and the
 * waist, so a moving hand cannot become a small standalone ROI. */
static void pose_update_person_roi(const u8 *frame, PersonRoi *person)
{
    u32 y, x, cell;
    u32 total_motion = 0U, weighted_x = 0U, weighted_y = 0U;
    s32 active_left = (s32)POSE_INPUT_WIDTH;
    s32 active_right = -1;
    s32 active_top = (s32)POSE_INPUT_HEIGHT;
    s32 active_bottom = -1;

    memset(pose_motion_cells, 0, sizeof(pose_motion_cells));
    for (y = 0; y < POSE_INPUT_HEIGHT; ++y) {
        for (x = 0; x < POSE_INPUT_WIDTH; ++x) {
            u32 pixel_index = y * POSE_INPUT_WIDTH + x;
            u8 gray = pose_gray_pixel(frame + pixel_index * 3U);
            if (person->initialized) {
                s32 delta = (s32)gray - (s32)pose_previous_gray[pixel_index];
                if (delta < 0)
                    delta = -delta;
                if (delta > 24) {
                    cell = (y >> 3) * POSE_GRID_WIDTH + (x >> 3);
                    if (pose_motion_cells[cell] < 255U)
                        ++pose_motion_cells[cell];
                }
            }
            pose_previous_gray[pixel_index] = gray;
        }
    }

    if (!person->initialized) {
        person->x = 40;
        person->y = 18;
        person->width = 176;
        person->height = 99;
        person->motion_pixels = 0U;
        person->initialized = 1U;
        memset(pose_motion_history, 0, sizeof(pose_motion_history));
        return;
    }

    for (cell = 0; cell < POSE_GRID_CELLS; ++cell) {
        u32 history = ((u32)pose_motion_history[cell] * 3U) >> 2;
        u32 addition = (u32)pose_motion_cells[cell] * 2U;
        s32 cell_x = (s32)(cell % POSE_GRID_WIDTH) * 8 + 4;
        s32 cell_y = (s32)(cell / POSE_GRID_WIDTH) * 8 + 4;
        if (history + addition > 255U)
            history = 255U;
        else
            history += addition;
        pose_motion_history[cell] = (u8)history;

        /* Only motion near the locked operator can steer the window. */
        if (history < 18U ||
            cell_x < person->x - 16 ||
            cell_x >= person->x + person->width + 16 ||
            cell_y < person->y - 12 ||
            cell_y >= person->y + person->height + 12)
            continue;
        total_motion += history;
        weighted_x += history * (u32)cell_x;
        weighted_y += history * (u32)cell_y;
        if (cell_x < active_left)
            active_left = cell_x;
        if (cell_x > active_right)
            active_right = cell_x;
        if (cell_y < active_top)
            active_top = cell_y;
        if (cell_y > active_bottom)
            active_bottom = cell_y;
    }

    if (total_motion >= 80U) {
        s32 old_center_x = person->x + person->width / 2;
        s32 old_center_y = person->y + person->height / 2;
        s32 target_center_x = (s32)(weighted_x / total_motion);
        s32 target_center_y = (s32)(weighted_y / total_motion);
        s32 extent_width = active_right - active_left + 56;
        s32 extent_height = active_bottom - active_top + 40;
        s32 target_width = extent_width;
        s32 new_width, new_height, new_center_x, new_center_y;
        if ((extent_height * 16) / 9 > target_width)
            target_width = (extent_height * 16) / 9;
        target_width = pose_clamp_s32(target_width, 176, 208);
        target_center_x = pose_clamp_s32(target_center_x,
                                         old_center_x - 8, old_center_x + 8);
        target_center_y = pose_clamp_s32(target_center_y,
                                         old_center_y - 6, old_center_y + 6);
        new_center_x = (old_center_x * 3 + target_center_x) / 4;
        new_center_y = (old_center_y * 3 + target_center_y) / 4;
        if (target_width > person->width)
            new_width = (person->width * 3 + target_width) / 4;
        else if (person->width > 176)
            new_width = person->width - 1;
        else
            new_width = person->width;
        person->width = pose_clamp_s32(new_width, 176, 208);
        person->height = (person->width * 9) / 16;
        new_height = person->height;
        person->x = pose_clamp_s32(new_center_x - person->width / 2, 0,
                                   (s32)POSE_INPUT_WIDTH - person->width);
        person->y = pose_clamp_s32(new_center_y - new_height / 2, 0,
                                   (s32)POSE_INPUT_HEIGHT - new_height);
        person->motion_pixels = total_motion;
    } else {
        person->motion_pixels = 0U;
    }
}

/* No second upper-half crop: copy the tracked visible-subject ROI exactly. */
static void pose_make_model_roi(const PersonRoi *person, PoseRoi *roi)
{
    roi->x = person->x;
    roi->y = person->y;
    roi->width = person->width;
    roi->height = person->height;
    roi->motion_pixels = person->motion_pixels;
    roi->initialized = person->initialized;
}

/* Head is the most reliable channel in the measured model.  When its
 * relationship to the shoulders is plausible, use it as a slow anchor so a
 * moving curtain or a bystander cannot drag the person window away. */
static void pose_track_person_from_head(PersonRoi *person,
                                        const PoseRoi *upper,
                                        const PosePoint *points)
{
    s32 head_x = points[0].x / 5;
    s32 head_y = points[0].y / 5;
    s32 shoulder_y = (points[1].y + points[2].y) / 2;
    s32 centre_x = person->x + person->width / 2;
    s32 target_y;
    if (points[0].logit_milli < POSE_LOGIT_THRESHOLD_MILLI ||
        head_x < upper->x || head_x >= upper->x + upper->width ||
        head_y < upper->y || head_y >= upper->y + upper->height / 2 ||
        points[0].y + 15 >= shoulder_y)
        return;
    head_x = pose_clamp_s32(head_x, centre_x - 12, centre_x + 12);
    if (pose_abs_s32(head_x - centre_x) > 4) {
        centre_x += (head_x - centre_x) / 4;
        person->x = pose_clamp_s32(centre_x - person->width / 2, 0,
                                   (s32)POSE_INPUT_WIDTH - person->width);
    }
    /* Keep the detected head near the upper quarter of the next ROI. */
    target_y = pose_clamp_s32(head_y - person->height / 4,
                              person->y - 4, person->y + 4);
    if (pose_abs_s32(target_y - person->y) > 2)
        person->y = pose_clamp_s32(person->y + (target_y - person->y) / 4,
                                   0, (s32)POSE_INPUT_HEIGHT - person->height);
}

static void pose_crop_roi(const u8 *frame, const PoseRoi *roi, u8 *output)
{
    u32 y, x;
    for (y = 0; y < POSE_INPUT_HEIGHT; ++y) {
        u32 source_y = (u32)roi->y +
                       ((2U * y + 1U) * (u32)roi->height) /
                       (2U * POSE_INPUT_HEIGHT);
        for (x = 0; x < POSE_INPUT_WIDTH; ++x) {
            u32 source_x = (u32)roi->x +
                           ((2U * x + 1U) * (u32)roi->width) /
                           (2U * POSE_INPUT_WIDTH);
            const u8 *source = frame + (source_y * POSE_INPUT_WIDTH + source_x) * 3U;
            u8 *destination = output + (y * POSE_INPUT_WIDTH + x) * 3U;
            destination[0] = source[0];
            destination[1] = source[1];
            destination[2] = source[2];
        }
    }
}

/* The VDMA stores B,G,R bytes; the trained network expects R,G,B channels. */
static void pose_input_conv(const u8 *input, float *output)
{
    u32 oy, ox, oc, ky, kx, ic;
    for (oy = 0; oy < 72U; ++oy) {
        for (ox = 0; ox < 128U; ++ox) {
            for (oc = 0; oc < POSE_STEM_CHANNELS; ++oc) {
                float sum = pose_stem_b[oc];
                for (ky = 0; ky < 3U; ++ky) {
                    s32 iy = (s32)(oy * 2U + ky) - 1;
                    if (iy < 0 || iy >= (s32)POSE_INPUT_HEIGHT)
                        continue;
                    for (kx = 0; kx < 3U; ++kx) {
                        s32 ix = (s32)(ox * 2U + kx) - 1;
                        const u8 *pixel;
                        const float *weight;
                        if (ix < 0 || ix >= (s32)POSE_INPUT_WIDTH)
                            continue;
                        pixel = input + (((u32)iy * POSE_INPUT_WIDTH + (u32)ix) * 3U);
                        weight = pose_stem_w + ((((oc * 3U) + ky) * 3U + kx) * 3U);
                        for (ic = 0; ic < 3U; ++ic)
                            sum += pose_input_lut[pixel[2U - ic]] * weight[ic];
                    }
                }
                output[(oy * 128U + ox) * POSE_STEM_CHANNELS + oc] = pose_relu(sum);
            }
        }
    }
}

static void pose_depthwise3x3(const float *input, u32 height, u32 width,
                              u32 channels, u32 stride, const float *weight,
                              const float *bias, float *output)
{
    u32 out_height = height / stride;
    u32 out_width = width / stride;
    u32 oy, ox, channel, ky, kx;
    for (oy = 0; oy < out_height; ++oy) {
        for (ox = 0; ox < out_width; ++ox) {
            for (channel = 0; channel < channels; ++channel) {
                float sum = bias[channel];
                for (ky = 0; ky < 3U; ++ky) {
                    s32 iy = (s32)(oy * stride + ky) - 1;
                    if (iy < 0 || iy >= (s32)height)
                        continue;
                    for (kx = 0; kx < 3U; ++kx) {
                        s32 ix = (s32)(ox * stride + kx) - 1;
                        if (ix < 0 || ix >= (s32)width)
                            continue;
                        sum += input[((u32)iy * width + (u32)ix) * channels + channel] *
                               weight[channel * 9U + ky * 3U + kx];
                    }
                }
                output[(oy * out_width + ox) * channels + channel] = pose_relu(sum);
            }
        }
    }
}

static void pose_pointwise(const float *input, u32 pixels, u32 input_channels,
                           u32 output_channels, const float *weight,
                           const float *bias, float *output)
{
    u32 pixel, oc, ic;
    for (pixel = 0; pixel < pixels; ++pixel) {
        const float *source = input + pixel * input_channels;
        float *destination = output + pixel * output_channels;
        for (oc = 0; oc < output_channels; ++oc) {
            float sum = bias[oc];
            const float *kernel = weight + oc * input_channels;
            for (ic = 0; ic < input_channels; ++ic)
                sum += source[ic] * kernel[ic];
            destination[oc] = pose_relu(sum);
        }
    }
}

static void pose_add(float *destination, const float *residual, u32 count)
{
    u32 index;
    for (index = 0; index < count; ++index)
        destination[index] += residual[index];
}

static void pose_decode_head(const float *input, const PoseRoi *roi, PosePoint *points)
{
    u32 keypoint, pixel, channel;

    /* Decode each trained heatmap independently.  Do not manufacture a
     * second limb from a weak distant peak: validation showed that doing so
     * creates long false segments even though it makes the two points look
     * separated.  Temporal/geometric validation is applied afterwards. */
    for (keypoint = 0; keypoint < POSE_KEYPOINTS; ++keypoint) {
        const float *kernel = pose_head_w + keypoint * POSE_HIGH_CHANNELS;
        float best = -3.402823466e+38f;
        u32 best_pixel = 0U;
        for (pixel = 0; pixel < POSE_HEATMAP_WIDTH * POSE_HEATMAP_HEIGHT; ++pixel) {
            const float *source = input + pixel * POSE_HIGH_CHANNELS;
            float sum = pose_head_b[keypoint];
            for (channel = 0; channel < POSE_HIGH_CHANNELS; ++channel)
                sum += source[channel] * kernel[channel];
            if (sum > best) {
                best = sum;
                best_pixel = pixel;
            }
        }
        {
            float model_x = (float)(best_pixel % POSE_HEATMAP_WIDTH) * 4.0f + 1.5f;
            float model_y = (float)(best_pixel / POSE_HEATMAP_WIDTH) * 4.0f + 1.5f;
            float source_x = (float)roi->x + model_x * (float)roi->width /
                             (float)POSE_INPUT_WIDTH;
            float source_y = (float)roi->y + model_y * (float)roi->height /
                             (float)POSE_INPUT_HEIGHT;
            points[keypoint].x = (s32)(source_x * 5.0f + 0.5f);
            points[keypoint].y = (s32)(source_y * 5.0f + 0.5f);
        }
        {
            points[keypoint].logit_milli = (s32)(best * 1000.0f);
        }
    }
}

static void pose_infer_ps(const u8 *input, const PoseRoi *roi, PosePoint *points)
{
    u32 y, x, channel;
    pose_input_conv(input, pose_feature0);
    pose_depthwise3x3(pose_feature0, 72U, 128U, POSE_STEM_CHANNELS, 2U,
                      pose_high_dw_w, pose_high_dw_b, pose_feature1);
    pose_pointwise(pose_feature1, 64U * 36U, POSE_STEM_CHANNELS, POSE_HIGH_CHANNELS,
                   pose_high_pw_w, pose_high_pw_b, pose_high);

#if POSE_MODEL_ARCH == 2
    pose_depthwise3x3(pose_high, 36U, 64U, POSE_HIGH_CHANNELS, 1U,
                      pose_highref0_dw_w, pose_highref0_dw_b, pose_feature0);
    pose_pointwise(pose_feature0, 64U * 36U, POSE_HIGH_CHANNELS, POSE_HIGH_CHANNELS,
                   pose_highref0_pw_w, pose_highref0_pw_b, pose_feature1);
    pose_add(pose_feature1, pose_high, POSE_HIGH_FEATURE);
    pose_depthwise3x3(pose_feature1, 36U, 64U, POSE_HIGH_CHANNELS, 1U,
                      pose_highref1_dw_w, pose_highref1_dw_b, pose_feature0);
    pose_pointwise(pose_feature0, 64U * 36U, POSE_HIGH_CHANNELS, POSE_HIGH_CHANNELS,
                   pose_highref1_pw_w, pose_highref1_pw_b, pose_high);
    pose_add(pose_high, pose_feature1, POSE_HIGH_FEATURE);
#endif

    pose_depthwise3x3(pose_high, 36U, 64U, POSE_HIGH_CHANNELS, 2U,
                      pose_low0_dw_w, pose_low0_dw_b, pose_feature0);
    pose_pointwise(pose_feature0, 32U * 18U, POSE_HIGH_CHANNELS, POSE_LOW_CHANNELS,
                   pose_low0_pw_w, pose_low0_pw_b, pose_feature1);

    pose_depthwise3x3(pose_feature1, 18U, 32U, POSE_LOW_CHANNELS, 1U,
                      pose_low1_dw_w, pose_low1_dw_b, pose_feature0);
    pose_pointwise(pose_feature0, 32U * 18U, POSE_LOW_CHANNELS, POSE_LOW_CHANNELS,
                   pose_low1_pw_w, pose_low1_pw_b, pose_low_extra);
    pose_add(pose_low_extra, pose_feature1, POSE_LOW_FEATURE);

    pose_depthwise3x3(pose_low_extra, 18U, 32U, POSE_LOW_CHANNELS, 1U,
                      pose_low2_dw_w, pose_low2_dw_b, pose_feature0);
    pose_pointwise(pose_feature0, 32U * 18U, POSE_LOW_CHANNELS, POSE_LOW_CHANNELS,
                   pose_low2_pw_w, pose_low2_pw_b, pose_feature1);
    pose_add(pose_feature1, pose_low_extra, POSE_LOW_FEATURE);

#if POSE_MODEL_ARCH == 2
    pose_depthwise3x3(pose_feature1, 18U, 32U, POSE_LOW_CHANNELS, 1U,
                      pose_low3_dw_w, pose_low3_dw_b, pose_feature0);
    pose_pointwise(pose_feature0, 32U * 18U, POSE_LOW_CHANNELS, POSE_LOW_CHANNELS,
                   pose_low3_pw_w, pose_low3_pw_b, pose_low_extra);
    pose_add(pose_low_extra, pose_feature1, POSE_LOW_FEATURE);
    pose_pointwise(pose_low_extra, 32U * 18U, POSE_LOW_CHANNELS, POSE_HIGH_CHANNELS,
                   pose_context_w, pose_context_b, pose_feature0);
#else
    pose_pointwise(pose_feature1, 32U * 18U, POSE_LOW_CHANNELS, POSE_HIGH_CHANNELS,
                   pose_context_w, pose_context_b, pose_feature0);
#endif
    for (y = 0; y < 36U; ++y) {
        for (x = 0; x < 64U; ++x) {
            const float *context = pose_feature0 +
                                   (((y >> 1) * 32U + (x >> 1)) * POSE_HIGH_CHANNELS);
            float *high = pose_high + ((y * 64U + x) * POSE_HIGH_CHANNELS);
            for (channel = 0; channel < POSE_HIGH_CHANNELS; ++channel)
                high[channel] += context[channel];
        }
    }

    pose_depthwise3x3(pose_high, 36U, 64U, POSE_HIGH_CHANNELS, 1U,
                      pose_ref0_dw_w, pose_ref0_dw_b, pose_feature0);
    pose_pointwise(pose_feature0, 64U * 36U, POSE_HIGH_CHANNELS, POSE_HIGH_CHANNELS,
                   pose_ref0_pw_w, pose_ref0_pw_b, pose_feature1);
    pose_add(pose_feature1, pose_high, POSE_HIGH_FEATURE);

    pose_depthwise3x3(pose_feature1, 36U, 64U, POSE_HIGH_CHANNELS, 1U,
                      pose_ref1_dw_w, pose_ref1_dw_b, pose_feature0);
    pose_pointwise(pose_feature0, 64U * 36U, POSE_HIGH_CHANNELS, POSE_HIGH_CHANNELS,
                   pose_ref1_pw_w, pose_ref1_pw_b, pose_high);
    pose_add(pose_high, pose_feature1, POSE_HIGH_FEATURE);
#if POSE_MODEL_ARCH == 2
    pose_depthwise3x3(pose_high, 36U, 64U, POSE_HIGH_CHANNELS, 1U,
                      pose_ref2_dw_w, pose_ref2_dw_b, pose_feature0);
    pose_pointwise(pose_feature0, 64U * 36U, POSE_HIGH_CHANNELS, POSE_HIGH_CHANNELS,
                   pose_ref2_pw_w, pose_ref2_pw_b, pose_feature1);
    pose_add(pose_feature1, pose_high, POSE_HIGH_FEATURE);
    pose_decode_head(pose_feature1, roi, points);
#else
    pose_decode_head(pose_high, roi, points);
#endif
}

static void pose_cnn_write_pointer(u32 base, u32 offset, const void *pointer)
{
    Xil_Out32(base + offset, (u32)(UINTPTR)pointer);
    Xil_Out32(base + offset + 4U, 0U);
}

static int pose_cnn_launch(const void *input_raw, const void *input,
                           const void *input_lut, const void *dw_weights,
                           const void *dw_params, const void *pw_weights,
                           const void *pw_params, const void *residual,
                           void *output, u32 operation, u32 height, u32 width,
                           u32 input_channels, u32 output_channels, u32 stride,
                           u32 input_zp, u32 dw_output_zp, u32 output_zp,
                           u32 residual_zp, u32 residual_mult,
                           u32 residual_shift, u32 relu_enable,
                           u32 residual_enable)
{
    const u32 base = XPAR_POSE_CNN_ACCEL_0_S_AXI_CONTROL_BASEADDR;
    u32 timeout = 0U;
    pose_cnn_write_pointer(base, POSE_CNN_REG_INPUT_RAW, input_raw);
    pose_cnn_write_pointer(base, POSE_CNN_REG_INPUT, input);
    pose_cnn_write_pointer(base, POSE_CNN_REG_INPUT_LUT, input_lut);
    pose_cnn_write_pointer(base, POSE_CNN_REG_DW_WEIGHTS, dw_weights);
    pose_cnn_write_pointer(base, POSE_CNN_REG_DW_PARAMS, dw_params);
    pose_cnn_write_pointer(base, POSE_CNN_REG_PW_WEIGHTS, pw_weights);
    pose_cnn_write_pointer(base, POSE_CNN_REG_PW_PARAMS, pw_params);
    pose_cnn_write_pointer(base, POSE_CNN_REG_RESIDUAL, residual);
    pose_cnn_write_pointer(base, POSE_CNN_REG_OUTPUT, output);
    Xil_Out32(base + POSE_CNN_REG_OPERATION, operation);
    Xil_Out32(base + POSE_CNN_REG_HEIGHT, height);
    Xil_Out32(base + POSE_CNN_REG_WIDTH, width);
    Xil_Out32(base + POSE_CNN_REG_INPUT_CHANNELS, input_channels);
    Xil_Out32(base + POSE_CNN_REG_OUTPUT_CHANNELS, output_channels);
    Xil_Out32(base + POSE_CNN_REG_STRIDE, stride);
    Xil_Out32(base + POSE_CNN_REG_INPUT_ZP, input_zp);
    Xil_Out32(base + POSE_CNN_REG_DW_OUTPUT_ZP, dw_output_zp);
    Xil_Out32(base + POSE_CNN_REG_OUTPUT_ZP, output_zp);
    Xil_Out32(base + POSE_CNN_REG_RESIDUAL_ZP, residual_zp);
    Xil_Out32(base + POSE_CNN_REG_RESIDUAL_MULT, residual_mult);
    Xil_Out32(base + POSE_CNN_REG_RESIDUAL_SHIFT, residual_shift);
    Xil_Out32(base + POSE_CNN_REG_RELU_ENABLE, relu_enable);
    Xil_Out32(base + POSE_CNN_REG_RESIDUAL_ENABLE, residual_enable);
    Xil_Out32(base + POSE_CNN_REG_CONTROL, 1U);
    while ((Xil_In32(base + POSE_CNN_REG_CONTROL) & 0x2U) == 0U) {
        if (++timeout > 200000000U)
            return -1;
    }
    return 0;
}

static void pose_decode_heatmaps(const u8 *heatmaps, const PoseRoi *roi,
                                 PosePoint *points)
{
    u32 keypoint, pixel;
    for (keypoint = 0; keypoint < POSE_KEYPOINTS; ++keypoint) {
        s32 best = -1;
        u32 best_pixel = 0U;
        for (pixel = 0; pixel < POSE_HEATMAP_WIDTH * POSE_HEATMAP_HEIGHT; ++pixel) {
            s32 value = heatmaps[pixel * POSE_Q_HEATMAP_STRIDE + keypoint];
            if (value > best) {
                best = value;
                best_pixel = pixel;
            }
        }
        points[keypoint].x = roi->x * 5 +
            (s32)(((((best_pixel % POSE_HEATMAP_WIDTH) * 8U + 3U) *
                    (u32)roi->width * 5U + 256U) >> 9));
        /* The display is 5x the 256x144 model coordinate space.  Use a fixed
         * reciprocal for the Y scale so the decoder still has no divide. */
        {
            u32 heatmap_y = best_pixel / POSE_HEATMAP_WIDTH;
            u32 y_numerator = ((heatmap_y * 8U + 3U) *
                               (u32)roi->height * 5U) + 144U;
            u32 scaled_y = (u32)(((u64)y_numerator * 58255ULL) >> 24);
            points[keypoint].y = roi->y * 5 + (s32)scaled_y;
        }
        points[keypoint].logit_milli =
            (best - (s32)POSE_HEAD_OUTPUT_ZP) * POSE_HEAD_OUTPUT_SCALE_MILLI;
    }
}

static int pose_infer_pl(const u8 *input, const PoseRoi *roi, PosePoint *points)
{
    volatile PoseCnnHardwareStatus *status =
        (volatile PoseCnnHardwareStatus *)POSE_CNN_STATUS_ADDR;
    u32 layer = 0U;
    XTime start, end;

    status->magic = 0U;
    /* The CPU only modifies the cropped network input.  Weights are const ELF
     * data and intermediate feature maps stay owned by the PL master.  A
     * whole-cache flush here needlessly stalls every inference. */
    Xil_DCacheFlushRange((UINTPTR)input, POSE_INPUT_BYTES);
    XTime_GetTime(&start);

#define POSE_RUN_LAYER(call_expression) \
    do { \
        ++layer; \
        if ((call_expression) != 0) \
            goto pl_failure; \
    } while (0)

    POSE_RUN_LAYER(pose_cnn_launch(
        input, pose_q_feature0, pose_input_quant_lut_q,
        pose_input_quant_lut_q, pose_input_quant_lut_q, pose_stem_w_q,
        pose_stem_p_q, pose_q_feature0, pose_q_feature0, POSE_CNN_OP_STEM,
        144U, 256U, 3U, POSE_STEM_CHANNELS, 2U, POSE_STEM_INPUT_ZP, 0U,
        POSE_STEM_OUTPUT_ZP, 0U, 0U, 0U, 1U, 0U));
    POSE_RUN_LAYER(pose_cnn_launch(
        input, pose_q_feature0, pose_input_quant_lut_q, pose_high_dw_w_q,
        pose_high_dw_p_q, pose_high_pw_w_q, pose_high_pw_p_q, pose_q_feature0,
        pose_q_high, POSE_CNN_OP_DEPTHWISE, 72U, 128U, POSE_STEM_CHANNELS,
        POSE_HIGH_CHANNELS, 2U, POSE_HIGH_DW_INPUT_ZP,
        POSE_HIGH_DW_OUTPUT_ZP, POSE_HIGH_PW_OUTPUT_ZP, 0U, 0U, 0U, 1U, 0U));

#define POSE_RUN_FUSED(src, dst, name, macro, h, w, ch, res) \
    POSE_RUN_LAYER(pose_cnn_launch( \
        input, src, pose_input_quant_lut_q, name##_dw_w_q, name##_dw_p_q, \
        name##_pw_w_q, name##_pw_p_q, src, dst, POSE_CNN_OP_DEPTHWISE, \
        h, w, ch, ch, 1U, macro##_DW_INPUT_ZP, macro##_DW_OUTPUT_ZP, \
        macro##_PW_OUTPUT_ZP, res ? macro##_PW_RESIDUAL_ZP : 0U, \
        res ? macro##_PW_RESIDUAL_MULT : 0U, \
        res ? macro##_PW_RESIDUAL_SHIFT : 0U, 1U, res))

    POSE_RUN_FUSED(pose_q_high, pose_q_feature0, pose_highref0, POSE_HIGHREF0,
                   36U, 64U, POSE_HIGH_CHANNELS, 1U);
    POSE_RUN_FUSED(pose_q_feature0, pose_q_high, pose_highref1, POSE_HIGHREF1,
                   36U, 64U, POSE_HIGH_CHANNELS, 1U);

    POSE_RUN_LAYER(pose_cnn_launch(
        input, pose_q_high, pose_input_quant_lut_q, pose_low0_dw_w_q,
        pose_low0_dw_p_q, pose_low0_pw_w_q, pose_low0_pw_p_q, pose_q_high,
        pose_q_feature0, POSE_CNN_OP_DEPTHWISE, 36U, 64U,
        POSE_HIGH_CHANNELS, POSE_LOW_CHANNELS, 2U, POSE_LOW0_DW_INPUT_ZP,
        POSE_LOW0_DW_OUTPUT_ZP, POSE_LOW0_PW_OUTPUT_ZP, 0U, 0U, 0U, 1U, 0U));
    POSE_RUN_FUSED(pose_q_feature0, pose_q_feature1, pose_low1, POSE_LOW1,
                   18U, 32U, POSE_LOW_CHANNELS, 1U);
    POSE_RUN_FUSED(pose_q_feature1, pose_q_low_extra, pose_low2, POSE_LOW2,
                   18U, 32U, POSE_LOW_CHANNELS, 1U);
    POSE_RUN_FUSED(pose_q_low_extra, pose_q_feature0, pose_low3, POSE_LOW3,
                   18U, 32U, POSE_LOW_CHANNELS, 1U);

    POSE_RUN_LAYER(pose_cnn_launch(
        input, pose_q_feature0, pose_input_quant_lut_q,
        pose_input_quant_lut_q, pose_input_quant_lut_q, pose_context_w_q,
        pose_context_p_q, pose_q_feature0, pose_q_feature1,
        POSE_CNN_OP_POINTWISE, 18U, 32U, POSE_LOW_CHANNELS,
        POSE_HIGH_CHANNELS, 1U, POSE_CONTEXT_INPUT_ZP, 0U,
        POSE_CONTEXT_OUTPUT_ZP, 0U, 0U, 0U, 1U, 0U));
    POSE_RUN_LAYER(pose_cnn_launch(
        input, pose_q_feature1, pose_input_quant_lut_q,
        pose_input_quant_lut_q, pose_merge_input_p_q,
        pose_input_quant_lut_q, pose_input_quant_lut_q, pose_q_high,
        pose_q_feature0, POSE_CNN_OP_UPSAMPLE_ADD, 18U, 32U,
        POSE_HIGH_CHANNELS, POSE_HIGH_CHANNELS, 1U, POSE_MERGE_INPUT_ZP, 0U,
        POSE_MERGE_OUTPUT_ZP, POSE_MERGE_RESIDUAL_ZP,
        POSE_MERGE_RESIDUAL_MULT, POSE_MERGE_RESIDUAL_SHIFT, 0U, 0U));

    POSE_RUN_FUSED(pose_q_feature0, pose_q_feature1, pose_ref0, POSE_REF0,
                   36U, 64U, POSE_HIGH_CHANNELS, 1U);
    POSE_RUN_FUSED(pose_q_feature1, pose_q_feature0, pose_ref1, POSE_REF1,
                   36U, 64U, POSE_HIGH_CHANNELS, 1U);
    POSE_RUN_FUSED(pose_q_feature0, pose_q_feature1, pose_ref2, POSE_REF2,
                   36U, 64U, POSE_HIGH_CHANNELS, 1U);

#undef POSE_RUN_FUSED
    POSE_RUN_LAYER(pose_cnn_launch(
        input, pose_q_feature1, pose_input_quant_lut_q,
        pose_input_quant_lut_q, pose_input_quant_lut_q, pose_head_w_q,
        pose_head_p_q, pose_q_feature1, pose_q_heatmaps,
        POSE_CNN_OP_POINTWISE, 36U, 64U, POSE_HIGH_CHANNELS,
        POSE_KEYPOINTS, 1U, POSE_HEAD_INPUT_ZP, 0U, POSE_HEAD_OUTPUT_ZP,
        0U, 0U, 0U, 0U, 0U));

#undef POSE_RUN_LAYER
    Xil_DCacheInvalidateRange((UINTPTR)pose_q_heatmaps,
                              sizeof(pose_q_heatmaps));
    pose_decode_heatmaps(pose_q_heatmaps, roi, points);
    XTime_GetTime(&end);
    status->version = 2U;
    status->backend_pl = 1U;
    status->completed_layers = layer;
    status->failed_layer = 0U;
    status->inference_us = (u32)(((end - start) * 1000000ULL) /
                                 COUNTS_PER_SECOND);
    status->magic = POSE_CNN_STATUS_MAGIC;
    Xil_DCacheFlushRange(POSE_CNN_STATUS_ADDR, sizeof(*status));
    return 0;

pl_failure:
#undef POSE_RUN_LAYER
    XTime_GetTime(&end);
    status->version = 2U;
    status->backend_pl = 0U;
    status->completed_layers = layer - 1U;
    status->failed_layer = layer;
    status->inference_us = (u32)(((end - start) * 1000000ULL) /
                                 COUNTS_PER_SECOND);
    status->magic = POSE_CNN_STATUS_MAGIC;
    Xil_DCacheFlushRange(POSE_CNN_STATUS_ADDR, sizeof(*status));
    return -1;
}

static int pose_infer(const u8 *input, const PoseRoi *roi, PosePoint *points)
{
    int status = pose_infer_pl(input, roi, points);
#if POSE_VALIDATION_BUILD
    /* A validation image must never be produced by an unreported PS fallback:
     * the last successfully displayed PL result remains on HDMI on failure. */
    return status;
#else
    if (status != 0) {
        pose_infer_ps(input, roi, points);
        return 1;
    }
    return 0;
#endif
}

static s32 pose_abs_s32(s32 value)
{
    return value < 0 ? -value : value;
}

static s32 pose_pair_distance2(const PosePoint *points, u32 first, u32 second)
{
    s32 dx = points[first].x - points[second].x;
    s32 dy = points[first].y - points[second].y;
    return dx * dx + dy * dy;
}

static s32 pose_rounded_shift(s32 value, u32 shift)
{
    s32 magnitude;
    if (shift == 0U)
        return value;
    magnitude = value < 0 ? -value : value;
    magnitude = (magnitude + (1 << (shift - 1U))) >> shift;
    return value < 0 ? -magnitude : magnitude;
}

/* Reject transient left/right collapse and limit implausible jumps.  This does
 * not invent a missing limb: it holds the last geometrically usable position
 * until the network produces a separated pair again. */
static void pose_stabilize_points(const PosePoint *raw, const PoseRoi *upper)
{
    static const u8 pairs[][2] = {{1, 2}, {3, 4}, {5, 6}, {7, 8}};
    PosePoint candidate[POSE_KEYPOINTS];
    u32 index;
    memcpy(candidate, raw, sizeof(candidate));

    if (pose_display_ready) {
        for (index = 0; index < sizeof(pairs) / sizeof(pairs[0]); ++index) {
            u32 first = pairs[index][0];
            u32 second = pairs[index][1];
            s32 minimum = index == 3U ? upper->width / 4 : upper->width / 3;
            s32 minimum2 = minimum * minimum;
            if (pose_pair_distance2(candidate, first, second) < minimum2 &&
                pose_pair_distance2(pose_display_points, first, second) >= minimum2) {
                candidate[first] = pose_display_points[first];
                candidate[second] = pose_display_points[second];
            }
        }

        for (index = 0; index < POSE_KEYPOINTS; ++index) {
            s32 max_step = (index >= 3U && index <= 6U) ? 96 : 64;
            s32 confirm_step = (index >= 3U && index <= 6U) ? 52 : 40;
            s32 deadband = (index >= 3U && index <= 6U) ? 10 : 7;
            s32 dx, dy, largest;
            u32 moving = upper->motion_pixels >= 180U;
            if (candidate[index].logit_milli < POSE_LOGIT_THRESHOLD_MILLI) {
                candidate[index] = pose_display_points[index];
                pose_pending_valid[index] = 0U;
                continue;
            }
            dx = candidate[index].x - pose_display_points[index].x;
            dy = candidate[index].y - pose_display_points[index].y;

            /* A single remote heatmap peak is the main source of large static
             * jumps.  When the scene is still, require two nearby detections
             * before accepting it.  Real motion bypasses this confirmation. */
            largest = pose_abs_s32(dx);
            if (pose_abs_s32(dy) > largest)
                largest = pose_abs_s32(dy);
            if (!moving && largest > confirm_step) {
                if (!pose_pending_valid[index] ||
                    pose_abs_s32(candidate[index].x -
                                 pose_pending_points[index].x) > 24 ||
                    pose_abs_s32(candidate[index].y -
                                 pose_pending_points[index].y) > 24) {
                    pose_pending_points[index] = candidate[index];
                    pose_pending_valid[index] = 1U;
                    candidate[index] = pose_display_points[index];
                    continue;
                }
                pose_pending_valid[index] = 0U;
            } else {
                pose_pending_valid[index] = 0U;
            }

            if (pose_abs_s32(dx) > max_step)
                candidate[index].x = pose_display_points[index].x +
                                     (dx < 0 ? -max_step : max_step);
            if (pose_abs_s32(dy) > max_step)
                candidate[index].y = pose_display_points[index].y +
                                     (dy < 0 ? -max_step : max_step);
            dx = candidate[index].x - pose_display_points[index].x;
            dy = candidate[index].y - pose_display_points[index].y;
            if (!moving) {
                if (pose_abs_s32(dx) <= deadband)
                    dx = 0;
                else
                    dx += dx < 0 ? deadband : -deadband;
                if (pose_abs_s32(dy) <= deadband)
                    dy = 0;
                else
                    dy += dy < 0 ? deadband : -deadband;
                candidate[index].x = pose_display_points[index].x +
                                     pose_rounded_shift(dx, 2U);
                candidate[index].y = pose_display_points[index].y +
                                     pose_rounded_shift(dy, 2U);
            } else {
                /* Keep 75% of a confirmed moving-frame displacement. */
                candidate[index].x = pose_display_points[index].x + dx -
                                     pose_rounded_shift(dx, 2U);
                candidate[index].y = pose_display_points[index].y + dy -
                                     pose_rounded_shift(dy, 2U);
            }
        }
    }
    memcpy(pose_display_points, candidate, sizeof(candidate));
    pose_display_ready = 1U;
}

static void pose_put_color(u8 *frame, s32 x, s32 y, u8 blue, u8 green, u8 red)
{
    u8 *pixel;
    if (x < 0 || y < 0 || x >= (s32)VIDEO_WIDTH || y >= (s32)VIDEO_HEIGHT)
        return;
    pixel = frame + (((u32)y * VIDEO_WIDTH + (u32)x) * 3U);
    pixel[0] = blue;
    pixel[1] = green;
    pixel[2] = red;
}

static void pose_put_green(u8 *frame, s32 x, s32 y)
{
    pose_put_color(frame, x, y, 0U, 255U, 0U);
}

static void pose_draw_line(u8 *frame, PosePoint first, PosePoint second)
{
    s32 x0 = first.x;
    s32 y0 = first.y;
    s32 x1 = second.x;
    s32 y1 = second.y;
    s32 dx = x1 > x0 ? x1 - x0 : x0 - x1;
    s32 sx = x0 < x1 ? 1 : -1;
    s32 dy_abs = y1 > y0 ? y1 - y0 : y0 - y1;
    s32 dy = -dy_abs;
    s32 sy = y0 < y1 ? 1 : -1;
    s32 error = dx + dy;
    if (first.logit_milli < POSE_LOGIT_THRESHOLD_MILLI ||
        second.logit_milli < POSE_LOGIT_THRESHOLD_MILLI)
        return;
    for (;;) {
        pose_put_green(frame, x0, y0);
        pose_put_green(frame, x0 + 1, y0);
        pose_put_green(frame, x0 - 1, y0);
        pose_put_green(frame, x0, y0 + 1);
        pose_put_green(frame, x0, y0 - 1);
        if (x0 == x1 && y0 == y1)
            break;
        {
            s32 twice = 2 * error;
            if (twice >= dy) {
                error += dy;
                x0 += sx;
            }
            if (twice <= dx) {
                error += dx;
                y0 += sy;
            }
        }
    }
}

static void pose_draw_point(u8 *frame, PosePoint point)
{
    s32 dx, dy;
    if (point.logit_milli < POSE_LOGIT_THRESHOLD_MILLI)
        return;
    for (dy = -5; dy <= 5; ++dy)
        for (dx = -5; dx <= 5; ++dx)
            if (dx * dx + dy * dy <= 25)
                pose_put_green(frame, point.x + dx, point.y + dy);
}

static void pose_draw_skeleton(u8 *frame, const PosePoint *points)
{
    static const u8 edges[][2] = {
        {0, 1}, {0, 2}, {1, 2}, {1, 3}, {3, 5},
        {2, 4}, {4, 6}, {1, 7}, {2, 8}, {7, 8}
    };
    u32 index;
    for (index = 0; index < sizeof(edges) / sizeof(edges[0]); ++index)
        pose_draw_line(frame, points[edges[index][0]], points[edges[index][1]]);
    for (index = 0; index < POSE_KEYPOINTS; ++index)
        pose_draw_point(frame, points[index]);
}

static void pose_draw_roi(u8 *frame, const PoseRoi *roi)
{
    s32 left = roi->x * 5;
    s32 top = roi->y * 5;
    s32 right = (roi->x + roi->width) * 5 - 1;
    s32 bottom = (roi->y + roi->height) * 5 - 1;
    s32 x, y, thickness;
    for (thickness = 0; thickness < 3; ++thickness) {
        for (x = left; x <= right; ++x) {
            pose_put_color(frame, x, top + thickness, 0U, 255U, 255U);
            pose_put_color(frame, x, bottom - thickness, 0U, 255U, 255U);
        }
        for (y = top; y <= bottom; ++y) {
            pose_put_color(frame, left + thickness, y, 0U, 255U, 255U);
            pose_put_color(frame, right - thickness, y, 0U, 255U, 255U);
        }
    }
}

static int pose_switch_display_buffers(XAxiVdma *video_vdma, u32 capture_base)
{
    UINTPTR addresses[XAXIVDMA_MAX_FRAMESTORE];
    u32 current = XAxiVdma_CurrFrameStore(video_vdma, XAXIVDMA_WRITE) % 3U;
    u32 completed = (current + 2U) % 3U;
    u32 index;
    Xil_DCacheInvalidateRange(capture_base + completed * VIDEO_FRAME_BYTES,
                              VIDEO_FRAME_BYTES);
    for (index = 0; index < 3U; ++index) {
        memcpy((void *)(UINTPTR)(VIDEO_DISPLAY_BASE + index * VIDEO_FRAME_BYTES),
               (const void *)(UINTPTR)(capture_base + completed * VIDEO_FRAME_BYTES),
               VIDEO_FRAME_BYTES);
    }
    Xil_DCacheFlushRange(VIDEO_DISPLAY_BASE, VIDEO_FRAME_BYTES * 3U);
    for (index = 0; index < XAXIVDMA_MAX_FRAMESTORE; ++index)
        addresses[index] = VIDEO_DISPLAY_BASE + (index % 3U) * VIDEO_FRAME_BYTES;
    XAxiVdma_DmaStop(video_vdma, XAXIVDMA_READ);
    if (XAxiVdma_DmaSetBufferAddr(video_vdma, XAXIVDMA_READ, addresses) != XST_SUCCESS)
        return XST_FAILURE;
    if (XAxiVdma_DmaStart(video_vdma, XAXIVDMA_READ) != XST_SUCCESS)
        return XST_FAILURE;
    pose_display_buffer_index = 0U;
    return XAxiVdma_StartParking(video_vdma, 0, XAXIVDMA_READ);
}

static u32 pose_choose_display_buffer(XAxiVdma *video_vdma)
{
    u32 active = XAxiVdma_CurrFrameStore(video_vdma, XAXIVDMA_READ) % 3U;
    if (active != pose_display_buffer_index)
        return 3U - active - pose_display_buffer_index;
    return (active + 1U) % 3U;
}

static void pose_run_hardware_test(XAxiVdma *video_vdma, XAxiVdma *pose_vdma,
                                   u32 video_base, u32 pose_base)
{
    static const char *names[POSE_KEYPOINTS] = {
        "head", "left_shoulder", "right_shoulder", "left_elbow",
        "right_elbow", "left_wrist", "right_wrist", "left_hip", "right_hip"
    };
    static const u32 model_sha256[8] = {
        POSE_MODEL_SHA256_WORD_0, POSE_MODEL_SHA256_WORD_1,
        POSE_MODEL_SHA256_WORD_2, POSE_MODEL_SHA256_WORD_3,
        POSE_MODEL_SHA256_WORD_4, POSE_MODEL_SHA256_WORD_5,
        POSE_MODEL_SHA256_WORD_6, POSE_MODEL_SHA256_WORD_7
    };
    volatile PoseHardwareResult *result = (volatile PoseHardwareResult *)POSE_RESULT_ADDR;
    volatile PoseCnnHardwareStatus *cnn_status =
        (volatile PoseCnnHardwareStatus *)POSE_CNN_STATUS_ADDR;
    PersonRoi person = {40, 18, 176, 99, 0U, 0U};
    PoseRoi roi = {40, 18, 176, 99, 0U, 0U};
    u32 frame_counter = 0U;
    u32 snapshot_sequence = 0U;
    XTime previous_frame_time = 0;
    u32 frame_index;

    result->magic = 0U;
    Xil_DCacheFlushRange(POSE_RESULT_ADDR, sizeof(PoseHardwareResult));
    xil_printf("Waiting for stable camera frames before ROI tracking...\r\n");
    sleep(2);
    if (pose_switch_display_buffers(video_vdma, video_base) != XST_SUCCESS) {
        xil_printf("ERROR: failed to switch HDMI to overlay buffers.\r\n");
        return;
    }
    pose_make_input_lut();
    pose_display_ready = 0U;
    xil_printf("POSE_TRACK_READY: yellow=model upper-body ROI, no second crop.\r\n");

    for (;;) {
        u32 video_current = XAxiVdma_CurrFrameStore(video_vdma, XAXIVDMA_WRITE) % 3U;
        u32 pose_current = XAxiVdma_CurrFrameStore(pose_vdma, XAXIVDMA_WRITE) % 3U;
        u32 video_completed = (video_current + 2U) % 3U;
        u32 pose_completed = (pose_current + 2U) % 3U;
        u32 video_address = video_base + video_completed * VIDEO_FRAME_BYTES;
        u32 pose_address = pose_base + pose_completed * POSE_INPUT_BYTES;
        u32 display_target = pose_choose_display_buffer(video_vdma);
        u32 display_address = VIDEO_DISPLAY_BASE +
                              display_target * VIDEO_FRAME_BYTES;
        XTime start_time;
        u32 frame_period_us;
        int inference_status;

        Xil_DCacheInvalidateRange(video_address, VIDEO_FRAME_BYTES);
        Xil_DCacheInvalidateRange(pose_address, POSE_INPUT_BYTES);
        memcpy((void *)(UINTPTR)display_address,
               (const void *)(UINTPTR)video_address,
               VIDEO_FRAME_BYTES);
        pose_update_person_roi((const u8 *)(UINTPTR)pose_address, &person);
        pose_make_model_roi(&person, &roi);
        pose_crop_roi((const u8 *)(UINTPTR)pose_address, &roi, pose_model_input);

        XTime_GetTime(&start_time);
        frame_period_us = previous_frame_time == 0 ? 0U :
            (u32)(((start_time - previous_frame_time) * 1000000ULL) /
                  COUNTS_PER_SECOND);
        previous_frame_time = start_time;
        inference_status = pose_infer(pose_model_input, &roi, pose_current_points);
        ++frame_counter;

        if (inference_status != 0) {
            xil_printf("POSE_PL_FAILURE frame=%d backend=PL layers=%d failed_layer=%d infer_us=%d\r\n",
                       frame_counter, cnn_status->completed_layers,
                       cnn_status->failed_layer, cnn_status->inference_us);
            /* Do not park the newly copied display buffer.  HDMI therefore
             * keeps the last fully completed PL inference result visible. */
            continue;
        }

        pose_track_person_from_head(&person, &roi, pose_current_points);
        pose_stabilize_points(pose_current_points, &roi);

        pose_draw_roi((u8 *)(UINTPTR)display_address, &roi);
        pose_draw_skeleton((u8 *)(UINTPTR)display_address, pose_display_points);
        Xil_DCacheFlushRange(display_address, VIDEO_FRAME_BYTES);
        if (XAxiVdma_StartParking(video_vdma, display_target,
                                  XAXIVDMA_READ) == XST_SUCCESS)
            pose_display_buffer_index = display_target;

        /* Publish input, aligned INT8 heatmap, ROI, status and raw decoded
         * points as one versioned snapshot every 30 frames.  An odd sequence
         * marks an in-progress write; the host also checks the trailing copy. */
        if ((frame_counter % POSE_SNAPSHOT_INTERVAL) == 0U) {
            u32 publish_sequence = snapshot_sequence + 2U;
            result->magic = 0U;
            result->snapshot_sequence = publish_sequence | 1U;
            result->snapshot_sequence_end = publish_sequence | 1U;
            Xil_DCacheFlushRange(POSE_RESULT_ADDR, sizeof(PoseHardwareResult));

            memcpy((void *)(UINTPTR)POSE_DEBUG_INPUT_ADDR,
                   pose_model_input, POSE_INPUT_BYTES);
            memcpy((void *)(UINTPTR)POSE_DEBUG_HEATMAP_ADDR,
                   pose_q_heatmaps, POSE_Q_HEATMAP_FEATURE);
            Xil_DCacheFlushRange(POSE_DEBUG_INPUT_ADDR, POSE_INPUT_BYTES);
            Xil_DCacheFlushRange(POSE_DEBUG_HEATMAP_ADDR,
                                 POSE_Q_HEATMAP_FEATURE);

            result->version = POSE_RESULT_VERSION;
            result->struct_bytes = sizeof(PoseHardwareResult);
            for (frame_index = 0; frame_index < 8U; ++frame_index)
                result->model_sha256[frame_index] = model_sha256[frame_index];
            result->frame_counter = frame_counter;
            result->input_frame_index = pose_completed;
            result->elapsed_us = frame_period_us;
            result->backend_pl = cnn_status->backend_pl;
            result->completed_layers = cnn_status->completed_layers;
            result->failed_layer = cnn_status->failed_layer;
            result->inference_us = cnn_status->inference_us;
            result->input_address = POSE_DEBUG_INPUT_ADDR;
            result->input_bytes = POSE_INPUT_BYTES;
            result->heatmap_address = POSE_DEBUG_HEATMAP_ADDR;
            result->heatmap_bytes = POSE_Q_HEATMAP_FEATURE;
            result->roi_x = roi.x;
            result->roi_y = roi.y;
            result->roi_width = roi.width;
            result->roi_height = roi.height;
            result->motion_pixels = roi.motion_pixels;
            for (frame_index = 0; frame_index < POSE_KEYPOINTS; ++frame_index) {
                result->points[frame_index] = pose_current_points[frame_index];
            }
            result->snapshot_sequence_end = publish_sequence;
            Xil_DCacheFlushRange(POSE_RESULT_ADDR, sizeof(PoseHardwareResult));
            result->snapshot_sequence = publish_sequence;
            result->magic = POSE_RESULT_MAGIC;
            Xil_DCacheFlushRange(POSE_RESULT_ADDR, sizeof(PoseHardwareResult));
            snapshot_sequence = publish_sequence;

            xil_printf("POSE_STATUS snapshot=%d frame=%d backend=PL layers=%d failed_layer=%d infer_us=%d model_sha256=%s\r\n",
                       snapshot_sequence, frame_counter,
                       cnn_status->completed_layers, cnn_status->failed_layer,
                       cnn_status->inference_us, POSE_MODEL_SHA256);
            xil_printf("POSE_ROI x=%d y=%d w=%d h=%d motion=%d frame_period_us=%d\r\n",
                       roi.x, roi.y, roi.width, roi.height,
                       roi.motion_pixels, frame_period_us);
            for (frame_index = 0; frame_index < POSE_KEYPOINTS; ++frame_index) {
                xil_printf("  %s=%d,%d score=%d\r\n", names[frame_index],
                           pose_current_points[frame_index].x,
                           pose_current_points[frame_index].y,
                           pose_current_points[frame_index].logit_milli);
            }
        }
    }
}

#endif
