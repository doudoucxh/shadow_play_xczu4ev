`timescale 1ns / 1ps

module dvi_tx_usplus (
    input  wire        pixel_clk,
    input  wire        pixel_clk_2_5x,
    input  wire        pixel_clk_5x,
    input  wire        reset_n,
    input  wire [23:0] video_data,
    input  wire        video_hsync,
    input  wire        video_vsync,
    input  wire        video_de,
    output wire        tmds_clk_p,
    output wire        tmds_clk_n,
    output wire [2:0]  tmds_data_p,
    output wire [2:0]  tmds_data_n
);

wire reset;
wire [9:0] red_10bit;
wire [9:0] green_10bit;
wire [9:0] blue_10bit;
wire [3:0] serial_data;

asyn_rst_syn reset_sync (
    .reset_n   (reset_n),
    .clk       (pixel_clk),
    .syn_reset (reset)
);

dvi_encoder encoder_b (
    .clkin(pixel_clk), .rstin(reset), .din(video_data[7:0]),
    .c0(video_hsync), .c1(video_vsync), .de(video_de), .dout(blue_10bit)
);
dvi_encoder encoder_g (
    .clkin(pixel_clk), .rstin(reset), .din(video_data[15:8]),
    .c0(1'b0), .c1(1'b0), .de(video_de), .dout(green_10bit)
);
dvi_encoder encoder_r (
    .clkin(pixel_clk), .rstin(reset), .din(video_data[23:16]),
    .c0(1'b0), .c1(1'b0), .de(video_de), .dout(red_10bit)
);

serializer_10_to_1_usplus ser_b (
    .parallel_data(blue_10bit), .reset(reset), .pixel_clk(pixel_clk),
    .pixel_clk_5x(pixel_clk_5x), .pixel_clk_2_5x(pixel_clk_2_5x),
    .serial_data_out(serial_data[0])
);
serializer_10_to_1_usplus ser_g (
    .parallel_data(green_10bit), .reset(reset), .pixel_clk(pixel_clk),
    .pixel_clk_5x(pixel_clk_5x), .pixel_clk_2_5x(pixel_clk_2_5x),
    .serial_data_out(serial_data[1])
);
serializer_10_to_1_usplus ser_r (
    .parallel_data(red_10bit), .reset(reset), .pixel_clk(pixel_clk),
    .pixel_clk_5x(pixel_clk_5x), .pixel_clk_2_5x(pixel_clk_2_5x),
    .serial_data_out(serial_data[2])
);
serializer_10_to_1_usplus ser_clk (
    .parallel_data(10'b1111100000), .reset(reset), .pixel_clk(pixel_clk),
    .pixel_clk_5x(pixel_clk_5x), .pixel_clk_2_5x(pixel_clk_2_5x),
    .serial_data_out(serial_data[3])
);

// Keep the electrical standard in the board-level XDC.  Putting it on the
// primitive as well allows a stale module-reference DCP to preserve an old
// TMDS_33 value, which is invalid for these UltraScale+ HP I/O pins.
OBUFDS obuf_b (
    .I(serial_data[0]), .O(tmds_data_p[0]), .OB(tmds_data_n[0])
);
OBUFDS obuf_g (
    .I(serial_data[1]), .O(tmds_data_p[1]), .OB(tmds_data_n[1])
);
OBUFDS obuf_r (
    .I(serial_data[2]), .O(tmds_data_p[2]), .OB(tmds_data_n[2])
);
OBUFDS obuf_clk (
    .I(serial_data[3]), .O(tmds_clk_p), .OB(tmds_clk_n)
);

endmodule
