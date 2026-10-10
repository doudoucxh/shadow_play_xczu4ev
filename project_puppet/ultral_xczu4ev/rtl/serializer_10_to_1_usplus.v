`timescale 1ns / 1ps

// 10:1 TMDS gearbox for UltraScale+. Ten bits arrive at pixel_clk and are
// converted to five 4-bit words at 2.5x pixel clock. OSERDESE3 emits each
// nibble with DDR at 5x pixel clock.
module serializer_10_to_1_usplus (
    input  wire [9:0] parallel_data,
    input  wire       reset,
    input  wire       pixel_clk,
    input  wire       pixel_clk_5x,
    input  wire       pixel_clk_2_5x,
    output wire       serial_data_out
);

reg  [3:0] wr_addr;
reg  [3:0] rd_addr;
wire [9:0] rd_curr;
reg  [9:2] rd_last;
reg  [2:0] rd_ctrl_cnt;
reg  [3:0] tx_data;

always @(posedge pixel_clk) begin
    if (reset)
        wr_addr <= 4'd0;
    else
        wr_addr <= wr_addr + 1'b1;
end

always @(posedge pixel_clk_2_5x) begin
    rd_last[9:2] <= rd_curr[9:2];
end

always @(posedge pixel_clk_2_5x) begin
    if (reset) begin
        rd_ctrl_cnt <= 3'd0;
        rd_addr     <= 4'd0;
        tx_data     <= 4'd0;
    end else begin
        case (rd_ctrl_cnt)
            3'd0: begin
                tx_data     <= rd_curr[3:0];
                rd_ctrl_cnt <= 3'd1;
            end
            3'd1: begin
                rd_addr     <= rd_addr + 1'b1;
                tx_data     <= rd_curr[7:4];
                rd_ctrl_cnt <= 3'd2;
            end
            3'd2: begin
                tx_data     <= {rd_curr[1:0], rd_last[9:8]};
                rd_ctrl_cnt <= 3'd3;
            end
            3'd3: begin
                rd_addr     <= rd_addr + 1'b1;
                tx_data     <= rd_curr[5:2];
                rd_ctrl_cnt <= 3'd4;
            end
            default: begin
                tx_data     <= rd_last[9:6];
                rd_ctrl_cnt <= 3'd0;
            end
        endcase
    end
end

genvar bit_index;
generate
    for (bit_index = 0; bit_index < 10; bit_index = bit_index + 1) begin : g_tmds_ram
        RAM32X1D gearbox_ram (
            .D     (parallel_data[bit_index]),
            .WCLK  (pixel_clk),
            .WE    (!reset),
            .A0    (wr_addr[0]),
            .A1    (wr_addr[1]),
            .A2    (wr_addr[2]),
            .A3    (wr_addr[3]),
            .A4    (1'b0),
            .SPO   (),
            .DPRA0 (rd_addr[0]),
            .DPRA1 (rd_addr[1]),
            .DPRA2 (rd_addr[2]),
            .DPRA3 (rd_addr[3]),
            .DPRA4 (1'b0),
            .DPO   (rd_curr[bit_index])
        );
    end
endgenerate

OSERDESE3 #(
    .DATA_WIDTH         (4),
    .INIT               (1'b0),
    .IS_CLKDIV_INVERTED (1'b0),
    .IS_CLK_INVERTED    (1'b0),
    .IS_RST_INVERTED    (1'b0),
    .SIM_DEVICE         ("ULTRASCALE_PLUS")
) oserdes (
    .OQ     (serial_data_out),
    .T_OUT  (),
    .CLK    (pixel_clk_5x),
    .CLKDIV (pixel_clk_2_5x),
    .D      ({4'b0000, tx_data}),
    .RST    (reset),
    .T      (1'b0)
);

endmodule

