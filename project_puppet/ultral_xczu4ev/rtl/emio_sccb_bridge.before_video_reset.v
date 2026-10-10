`timescale 1ns / 1ps

// Expose only EMIO GPIO[1:0] as SCCB pins.  The Zynq UltraScale+ PS presents
// a fixed 95-bit EMIO GPIO bus even when the configured user width is two.
module emio_sccb_bridge (
    input  wire [94:0] gpio_o,
    input  wire [94:0] gpio_t,
    output wire [94:0] gpio_i,
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

endmodule
