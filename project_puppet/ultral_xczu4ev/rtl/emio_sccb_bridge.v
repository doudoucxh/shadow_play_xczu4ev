`timescale 1ns / 1ps

// Expose only EMIO GPIO[1:0] as SCCB pins.  The Zynq UltraScale+ PS presents
// a fixed 95-bit EMIO GPIO bus even when the configured user width is two.
module emio_sccb_bridge (
    input  wire [94:0] gpio_o,
    input  wire [94:0] gpio_t,
    output wire [94:0] gpio_i,
    output wire        video_in_resetn,
    inout  wire        sccb_scl,
    inout  wire        sccb_sda
);

    wire scl_i;
    wire sda_i;

    IOBUF scl_iobuf (
        .I  (gpio_o[0]),
        .T  (gpio_t[0]),
        .O  (scl_i),
        .IO (sccb_scl)
    );

    IOBUF sda_iobuf (
        .I  (gpio_o[1]),
        .T  (gpio_t[1]),
        .O  (sda_i),
        .IO (sccb_sda)
    );

    assign gpio_i = {93'b0, sda_i, scl_i};

    // EMIO GPIO[2] is a software-controlled active-low reset release for
    // Video In to AXI4-Stream.  While GPIO[2] is still an input, keep the
    // video bridge in reset so camera configuration cannot leave its async
    // state machine half-synchronized.
    assign video_in_resetn = (~gpio_t[2]) & gpio_o[2];

endmodule
