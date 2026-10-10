#include "../ultral_xczu4ev/vitis/ov5640_hdmi/src/pose_model_weights.h"
#include "../ultral_xczu4ev/vitis/ov5640_hdmi/src/pose_model_int8_weights.h"

static_assert(POSE_MODEL_ARCH == 2, "V2 model required");
static_assert(POSE_STEM_CHANNELS == 24U, "unexpected stem width");
static_assert(POSE_HIGH_CHANNELS == 32U, "unexpected high width");
static_assert(POSE_LOW_CHANNELS == 48U, "unexpected low width");

int main()
{
    return pose_stem_w[0] == 0.0f && pose_stem_w_q[0] == 0ULL;
}
