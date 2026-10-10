/* Device registers require one aligned 32-bit load/store, not a byte-buffer
 * serializer (which may clear/copy bytes before the intended value). No libc
 * dependency: this library also works with the board's existing Linux loader.
 */
_Static_assert(sizeof(unsigned int) == 4, "32-bit register type required");

static inline void device_barrier(void) {
#if defined(__aarch64__)
    __asm__ volatile("dsb sy" ::: "memory");
#else
    __sync_synchronize(); /* Allows ordinary RAM tests on the development VM. */
#endif
}

unsigned int servo_mmio_abi(void) { return 1; }

unsigned int servo_mmio_read32(void *base, unsigned int offset) {
    volatile unsigned int *reg = (volatile unsigned int *)((char *)base + offset);
    device_barrier();
    unsigned int value = *reg;
    device_barrier();
    return value;
}

void servo_mmio_write32(void *base, unsigned int offset, unsigned int value) {
    volatile unsigned int *reg = (volatile unsigned int *)((char *)base + offset);
    device_barrier();
    *reg = value;
    device_barrier();
}
