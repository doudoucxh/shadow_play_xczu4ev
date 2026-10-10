#include "shadow_hw_init.h"

#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>

#define GPIO_BASE 0xFF0A0000UL
#define VIDEO_VDMA_BASE 0xA0000000UL
#define POSE_VDMA_BASE 0xA0010000UL
#define VTC_BASE 0xA0020000UL

#define VIDEO_CAPTURE_BASE 0x70000000UL
#define VIDEO_DISPLAY_BASE 0x71000000UL
#define POSE_CAPTURE_BASE 0x72000000UL

#define VIDEO_WIDTH 1280U
#define VIDEO_HEIGHT 720U
#define POSE_WIDTH 256U
#define POSE_HEIGHT 144U
#define PIXEL_BYTES 3U
#define VIDEO_FRAME_BYTES (VIDEO_WIDTH * VIDEO_HEIGHT * PIXEL_BYTES)
#define POSE_FRAME_BYTES (POSE_WIDTH * POSE_HEIGHT * PIXEL_BYTES)

#define MAP_REG_BYTES 0x10000U
#define GPIO_MAP_BYTES 0x1000U
#define EMIO_SCL_PIN 78U
#define EMIO_SDA_PIN 79U
#define EMIO_VIDEO_RESET_PIN 80U

#define VDMA_CR 0x00U
#define VDMA_SR 0x04U
#define VDMA_PARKPTR 0x28U
#define VDMA_MM2S 0x00U
#define VDMA_S2MM 0x30U
#define VDMA_MM2S_START 0x50U
#define VDMA_S2MM_START 0xA0U
#define VDMA_VSIZE 0x00U
#define VDMA_HSIZE 0x04U
#define VDMA_STRIDE 0x08U
#define VDMA_ADDR0 0x0CU
#define VDMA_RESET 0x04U
#define VDMA_CIRCULAR 0x02U
#define VDMA_RUN 0x01U
#define VDMA_ERROR_MASK 0x00000FF0U

static volatile uint32_t *gpio_regs;

static void zero_physical(volatile void *base, size_t length)
{
    volatile uint32_t *words = (volatile uint32_t *)base;
    size_t count = length / sizeof(*words);
    size_t index;

    /* /dev/mem is mapped as device memory.  Avoid libc memset(), whose
     * AArch64 DC ZVA fast path may raise SIGBUS on this mapping type. */
    for (index = 0; index < count; ++index)
        words[index] = 0U;
    __sync_synchronize();
}

static void fill_physical(volatile void *base, size_t length, uint32_t value)
{
    volatile uint32_t *words = (volatile uint32_t *)base;
    size_t count = length / sizeof(*words);
    size_t index;

    for (index = 0; index < count; ++index)
        words[index] = value;
    __sync_synchronize();
}

static void *map_physical(int fd, uintptr_t address, size_t length)
{
    void *mapping = mmap(NULL, length, PROT_READ | PROT_WRITE,
                         MAP_SHARED, fd, (off_t)address);
    if (mapping == MAP_FAILED) {
        fprintf(stderr, "mmap 0x%lx (%zu bytes) failed: %s\n",
                (unsigned long)address, length, strerror(errno));
        exit(EXIT_FAILURE);
    }
    return mapping;
}

static inline uint32_t reg_read(volatile uint32_t *base, uint32_t offset)
{
    return base[offset / 4U];
}

static inline void reg_write(volatile uint32_t *base, uint32_t offset,
                             uint32_t value)
{
    base[offset / 4U] = value;
    __sync_synchronize();
}

static void gpio_bank_pin(uint32_t pin, uint32_t *bank, uint32_t *in_bank)
{
    static const uint32_t ends[] = {25U, 51U, 77U, 109U, 141U, 173U};
    uint32_t index = 0U;
    while (index < 6U && pin > ends[index])
        ++index;
    if (index >= 6U) {
        fprintf(stderr, "invalid GPIO pin %u\n", pin);
        exit(EXIT_FAILURE);
    }
    *bank = index;
    *in_bank = index == 0U ? pin : pin - ends[index - 1U] - 1U;
}

static void gpio_direction(uint32_t pin, int output)
{
    uint32_t bank, bit, offset, value;
    gpio_bank_pin(pin, &bank, &bit);
    offset = 0x204U + bank * 0x40U;
    value = reg_read(gpio_regs, offset);
    value = output ? value | (1U << bit) : value & ~(1U << bit);
    reg_write(gpio_regs, offset, value);
}

static void gpio_output_enable(uint32_t pin, int enabled)
{
    uint32_t bank, bit, offset, value;
    gpio_bank_pin(pin, &bank, &bit);
    offset = 0x208U + bank * 0x40U;
    value = reg_read(gpio_regs, offset);
    value = enabled ? value | (1U << bit) : value & ~(1U << bit);
    reg_write(gpio_regs, offset, value);
}

static void gpio_write(uint32_t pin, int high)
{
    uint32_t bank, bit, offset, value;
    gpio_bank_pin(pin, &bank, &bit);
    if (bit > 15U) {
        bit -= 16U;
        offset = bank * 8U + 4U;
    } else {
        offset = bank * 8U;
    }
    value = (~(1U << (bit + 16U))) &
            (((high ? 1U : 0U) << bit) | 0xFFFF0000U);
    reg_write(gpio_regs, offset, value);
}

static int gpio_read(uint32_t pin)
{
    uint32_t bank, bit;
    gpio_bank_pin(pin, &bank, &bit);
    return (reg_read(gpio_regs, 0x60U + bank * 4U) >> bit) & 1U;
}

void emio_init(void)
{
    gpio_direction(EMIO_VIDEO_RESET_PIN, 1);
    gpio_output_enable(EMIO_VIDEO_RESET_PIN, 1);
    gpio_write(EMIO_VIDEO_RESET_PIN, 0);

    gpio_direction(EMIO_SCL_PIN, 1);
    gpio_direction(EMIO_SDA_PIN, 1);
    gpio_output_enable(EMIO_SCL_PIN, 1);
    gpio_output_enable(EMIO_SDA_PIN, 1);
    gpio_write(EMIO_SCL_PIN, 1);
    gpio_write(EMIO_SDA_PIN, 1);
}

void sccb_start(void)
{
    gpio_write(EMIO_SCL_PIN, 1);
    gpio_write(EMIO_SDA_PIN, 1);
    usleep(4);
    gpio_write(EMIO_SDA_PIN, 0);
    usleep(4);
}

void sccb_stop(void)
{
    gpio_write(EMIO_SDA_PIN, 0);
    usleep(4);
    gpio_write(EMIO_SCL_PIN, 1);
    usleep(4);
    gpio_write(EMIO_SDA_PIN, 1);
    usleep(4);
}

void sccb_send_byte(u8 value)
{
    unsigned bit;
    gpio_write(EMIO_SCL_PIN, 0);
    for (bit = 0; bit < 8U; ++bit) {
        usleep(2);
        gpio_write(EMIO_SDA_PIN, (value & 0x80U) != 0U);
        value <<= 1;
        usleep(2);
        gpio_write(EMIO_SCL_PIN, 1);
        usleep(4);
        gpio_write(EMIO_SCL_PIN, 0);
    }
}

u8 sccb_rece_byte(void)
{
    unsigned bit;
    u8 value = 0U;
    gpio_direction(EMIO_SDA_PIN, 0);
    gpio_output_enable(EMIO_SDA_PIN, 0);
    for (bit = 0; bit < 8U; ++bit) {
        usleep(4);
        gpio_write(EMIO_SCL_PIN, 1);
        usleep(2);
        value = (u8)((value << 1) | (gpio_read(EMIO_SDA_PIN) ? 1U : 0U));
        usleep(2);
        gpio_write(EMIO_SCL_PIN, 0);
    }
    return value;
}

void sccb_ack(void)
{
    usleep(2);
    gpio_direction(EMIO_SDA_PIN, 0);
    gpio_output_enable(EMIO_SDA_PIN, 0);
    usleep(2);
    gpio_write(EMIO_SCL_PIN, 1);
    usleep(4);
    gpio_write(EMIO_SCL_PIN, 0);
    gpio_direction(EMIO_SDA_PIN, 1);
    gpio_output_enable(EMIO_SDA_PIN, 1);
}

void sccb_host_no_ack(void)
{
    usleep(2);
    gpio_direction(EMIO_SDA_PIN, 1);
    gpio_output_enable(EMIO_SDA_PIN, 1);
    gpio_write(EMIO_SDA_PIN, 1);
    usleep(2);
    gpio_write(EMIO_SCL_PIN, 1);
    usleep(4);
    gpio_write(EMIO_SCL_PIN, 0);
}

static int vdma_reset(volatile uint32_t *vdma, uint32_t channel)
{
    unsigned retry;
    reg_write(vdma, channel + VDMA_CR, VDMA_RESET);
    for (retry = 0; retry < 1000U; ++retry) {
        if ((reg_read(vdma, channel + VDMA_CR) & VDMA_RESET) == 0U)
            return 0;
        usleep(10);
    }
    return -1;
}

static int vdma_start(volatile uint32_t *vdma, uint32_t channel,
                      uint32_t start_regs, uintptr_t frame_base,
                      uint32_t frame_bytes, uint32_t stride, uint32_t height)
{
    unsigned index;
    if (vdma_reset(vdma, channel) != 0)
        return -1;
    reg_write(vdma, channel + VDMA_SR, 0xFFFFFFFFU);
    reg_write(vdma, channel + VDMA_CR, VDMA_CIRCULAR);
    reg_write(vdma, start_regs + VDMA_HSIZE, stride);
    reg_write(vdma, start_regs + VDMA_STRIDE, stride);
    for (index = 0; index < 3U; ++index)
        reg_write(vdma, start_regs + VDMA_ADDR0 + index * 4U,
                  (uint32_t)(frame_base + index * frame_bytes));
    reg_write(vdma, channel + VDMA_CR, VDMA_CIRCULAR | VDMA_RUN);
    reg_write(vdma, start_regs + VDMA_VSIZE, height);
    usleep(1000);
    return (reg_read(vdma, channel + VDMA_SR) & VDMA_ERROR_MASK) ? -1 : 0;
}

static void vtc_start_720p(volatile uint32_t *vtc)
{
    const uint32_t pair_shift = 16U;
    reg_write(vtc, 0x000U, 0x80000000U);
    usleep(10);
    reg_write(vtc, 0x000U, 0U);
    reg_write(vtc, 0x060U, 1280U | (720U << pair_shift));
    reg_write(vtc, 0x068U, 0U);
    reg_write(vtc, 0x06CU, 0x7FU);
    reg_write(vtc, 0x070U, 1650U);
    reg_write(vtc, 0x074U, 750U | (750U << pair_shift));
    reg_write(vtc, 0x078U, 1390U | (1430U << pair_shift));
    reg_write(vtc, 0x07CU, 1280U | (1280U << pair_shift));
    reg_write(vtc, 0x080U, 724U | (729U << pair_shift));
    reg_write(vtc, 0x084U, 1390U | (1390U << pair_shift));
    reg_write(vtc, 0x088U, 1280U | (1280U << pair_shift));
    reg_write(vtc, 0x08CU, 724U | (729U << pair_shift));
    reg_write(vtc, 0x090U, 1390U | (1390U << pair_shift));
    reg_write(vtc, 0x094U, 720U << pair_shift);
    reg_write(vtc, 0x000U, 0x03FDEF06U);
}

static void ov5640_print_video_state(void)
{
    printf("OV5640 state: 3008=%02x 3000=%02x 3004=%02x "
           "3035=%02x 3036=%02x 3037=%02x 3108=%02x\n",
           sccb_read_reg16(0x3008U), sccb_read_reg16(0x3000U),
           sccb_read_reg16(0x3004U), sccb_read_reg16(0x3035U),
           sccb_read_reg16(0x3036U), sccb_read_reg16(0x3037U),
           sccb_read_reg16(0x3108U));
    printf("OV5640 size: %02x%02x x %02x%02x total=%02x%02x/%02x%02x "
           "fmt=%02x isp=%02x pclk=%02x/%02x pattern=%02x\n",
           sccb_read_reg16(0x3808U), sccb_read_reg16(0x3809U),
           sccb_read_reg16(0x380AU), sccb_read_reg16(0x380BU),
           sccb_read_reg16(0x380CU), sccb_read_reg16(0x380DU),
           sccb_read_reg16(0x380EU), sccb_read_reg16(0x380FU),
           sccb_read_reg16(0x4300U), sccb_read_reg16(0x501FU),
           sccb_read_reg16(0x4837U), sccb_read_reg16(0x3824U),
           sccb_read_reg16(0x503DU));
}

int main(void)
{
    int fd;
    volatile uint32_t *video_vdma;
    volatile uint32_t *pose_vdma;
    volatile uint32_t *vtc;
    void *video_capture;
    void *video_display;
    void *pose_capture;
    int status = EXIT_FAILURE;

    fd = open("/dev/mem", O_RDWR | O_SYNC);
    if (fd < 0) {
        perror("open /dev/mem");
        return EXIT_FAILURE;
    }

    gpio_regs = map_physical(fd, GPIO_BASE, GPIO_MAP_BYTES);
    video_vdma = map_physical(fd, VIDEO_VDMA_BASE, MAP_REG_BYTES);
    pose_vdma = map_physical(fd, POSE_VDMA_BASE, MAP_REG_BYTES);
    vtc = map_physical(fd, VTC_BASE, MAP_REG_BYTES);
    video_capture = map_physical(fd, VIDEO_CAPTURE_BASE, VIDEO_FRAME_BYTES * 3U);
    video_display = map_physical(fd, VIDEO_DISPLAY_BASE, VIDEO_FRAME_BYTES * 3U);
    pose_capture = map_physical(fd, POSE_CAPTURE_BASE, POSE_FRAME_BYTES * 3U);

    zero_physical(video_capture, VIDEO_FRAME_BYTES * 3U);
    zero_physical(video_display, VIDEO_FRAME_BYTES * 3U);
    zero_physical(pose_capture, POSE_FRAME_BYTES * 3U);
    if (getenv("SHADOW_DISPLAY_TEST_PATTERN") != NULL) {
        fill_physical(video_display, VIDEO_FRAME_BYTES * 3U, 0xFFFFFFFFU);
        printf("HDMI display buffers filled white for diagnostics\n");
    }

    emio_init();
    if (ov5640_init(VIDEO_WIDTH, VIDEO_HEIGHT, 2570U, 980U) != 0U) {
        fprintf(stderr, "OV5640 initialization failed\n");
        goto done;
    }
    sccb_write_reg16(0x3820U, 0x40U);
    if (getenv("SHADOW_CAMERA_TEST_PATTERN") != NULL) {
        sccb_write_reg16(0x503DU, 0x80U);
        printf("OV5640 internal color bars enabled\n");
    }
    ov5640_print_video_state();

    /* The Video In to AXI4-Stream core must be reset while OV5640 is being
     * reconfigured.  Release it only after the sensor is producing its final
     * timing; otherwise its async input state machine can stop emitting
     * TVALID until the next PL reconfiguration. */
    gpio_write(EMIO_VIDEO_RESET_PIN, 1);
    usleep(1000);

    if (vdma_start(video_vdma, VDMA_S2MM, VDMA_S2MM_START,
                   VIDEO_CAPTURE_BASE, VIDEO_FRAME_BYTES,
                   VIDEO_WIDTH * PIXEL_BYTES, VIDEO_HEIGHT) != 0) {
        fprintf(stderr, "video S2MM failed\n");
        goto done;
    }
    if (vdma_start(video_vdma, VDMA_MM2S, VDMA_MM2S_START,
                   VIDEO_DISPLAY_BASE, VIDEO_FRAME_BYTES,
                   VIDEO_WIDTH * PIXEL_BYTES, VIDEO_HEIGHT) != 0) {
        fprintf(stderr, "video MM2S failed\n");
        goto done;
    }
    vtc_start_720p(vtc);
    if (vdma_start(pose_vdma, VDMA_S2MM, VDMA_S2MM_START,
                   POSE_CAPTURE_BASE, POSE_FRAME_BYTES,
                   POSE_WIDTH * PIXEL_BYTES, POSE_HEIGHT) != 0) {
        fprintf(stderr, "pose S2MM failed\n");
        goto done;
    }

    printf("SHADOW_HW_READY video=0x%08lx display=0x%08lx pose=0x%08lx\n",
           (unsigned long)VIDEO_CAPTURE_BASE,
           (unsigned long)VIDEO_DISPLAY_BASE,
           (unsigned long)POSE_CAPTURE_BASE);
    status = EXIT_SUCCESS;

done:
    munmap(pose_capture, POSE_FRAME_BYTES * 3U);
    munmap(video_display, VIDEO_FRAME_BYTES * 3U);
    munmap(video_capture, VIDEO_FRAME_BYTES * 3U);
    munmap((void *)vtc, MAP_REG_BYTES);
    munmap((void *)pose_vdma, MAP_REG_BYTES);
    munmap((void *)video_vdma, MAP_REG_BYTES);
    munmap((void *)gpio_regs, GPIO_MAP_BYTES);
    close(fd);
    return status;
}
