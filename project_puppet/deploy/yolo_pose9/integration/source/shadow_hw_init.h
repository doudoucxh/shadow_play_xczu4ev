#ifndef SHADOW_HW_INIT_H
#define SHADOW_HW_INIT_H

#include <stdint.h>
#include <stdio.h>
#include <unistd.h>

typedef uint8_t u8;
typedef uint16_t u16;

#define xil_printf printf

void emio_init(void);
void sccb_start(void);
void sccb_stop(void);
void sccb_ack(void);
void sccb_host_no_ack(void);
void sccb_send_byte(u8 value);
u8 sccb_rece_byte(void);
void sccb_write_reg16(u16 address, u8 value);
u8 sccb_read_reg16(u16 address);
u8 ov5640_init(u16 width, u16 height, u16 total_width, u16 total_height);

#endif
