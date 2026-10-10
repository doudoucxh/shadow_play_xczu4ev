`timescale 1ns / 1ps

// Full-frame preprocessing for the pose-estimation branch.
// Default mapping:
//   input  : 1280x720 RGB888 AXI4-Stream video
//   region : complete 16:9 frame
//   output : 256x144 RGB888, nearest-neighbour 5:1 decimation
// TUSER marks the first output pixel and TLAST marks each output line.
module pose_preprocess_axis #(
    parameter integer IN_WIDTH   = 1280,
    parameter integer IN_HEIGHT  = 720,
    parameter integer ROI_X      = 0,
    parameter integer ROI_Y      = 0,
    parameter integer OUT_WIDTH  = 256,
    parameter integer OUT_HEIGHT = 144,
    parameter integer SCALE      = 5
)(
    input  wire        aclk,
    input  wire        aresetn,

    input  wire [23:0] s_axis_tdata,
    input  wire        s_axis_tvalid,
    output wire        s_axis_tready,
    input  wire        s_axis_tuser,
    input  wire        s_axis_tlast,

    output wire [23:0] m_axis_tdata,
    output wire        m_axis_tvalid,
    input  wire        m_axis_tready,
    output wire        m_axis_tuser,
    output wire        m_axis_tlast
);

localparam integer X_BITS = (IN_WIDTH  <= 2) ? 1 : $clog2(IN_WIDTH);
localparam integer Y_BITS = (IN_HEIGHT <= 2) ? 1 : $clog2(IN_HEIGHT);
localparam integer ROI_LAST_X = ROI_X + (OUT_WIDTH  - 1) * SCALE;
localparam integer ROI_LAST_Y = ROI_Y + (OUT_HEIGHT - 1) * SCALE;

reg [X_BITS-1:0] x_pos;
reg [Y_BITS-1:0] y_pos;
reg [X_BITS-1:0] next_sample_x;
reg [Y_BITS-1:0] next_sample_y;

reg [23:0] out_data;
reg        out_valid;
reg        out_user;
reg        out_last;

wire [X_BITS-1:0] pixel_x = s_axis_tuser ? {X_BITS{1'b0}} : x_pos;
wire [Y_BITS-1:0] pixel_y = s_axis_tuser ? {Y_BITS{1'b0}} : y_pos;
wire [X_BITS-1:0] target_x = s_axis_tuser ? ROI_X : next_sample_x;
wire [Y_BITS-1:0] target_y = s_axis_tuser ? ROI_Y : next_sample_y;

// Equality against the next sampling coordinate replaces division/modulo
// logic and keeps the path short at the 100 MHz video clock.
wire sample_pixel = (pixel_x == target_x) && (pixel_y == target_y) &&
                    (pixel_x <= ROI_LAST_X) && (pixel_y <= ROI_LAST_Y);

// Unsampled input pixels can be discarded while an output pixel is waiting.
// A sampled pixel applies normal AXI4-Stream backpressure.
assign s_axis_tready = !sample_pixel || !out_valid || m_axis_tready;
wire input_fire = s_axis_tvalid && s_axis_tready;

assign m_axis_tdata  = out_data;
assign m_axis_tvalid = out_valid;
assign m_axis_tuser  = out_user;
assign m_axis_tlast  = out_last;

always @(posedge aclk) begin
    if (!aresetn) begin
        x_pos     <= {X_BITS{1'b0}};
        y_pos     <= {Y_BITS{1'b0}};
        next_sample_x <= ROI_X;
        next_sample_y <= ROI_Y;
        out_data  <= 24'd0;
        out_valid <= 1'b0;
        out_user  <= 1'b0;
        out_last  <= 1'b0;
    end else begin
        if (out_valid && m_axis_tready)
            out_valid <= 1'b0;

        if (input_fire) begin
            if (sample_pixel) begin
                out_data  <= s_axis_tdata;
                out_valid <= 1'b1;
                out_user  <= (pixel_x == ROI_X) && (pixel_y == ROI_Y);
                out_last  <= (pixel_x == ROI_LAST_X);
            end

            if (s_axis_tuser) begin
                next_sample_x <= ROI_X;
                next_sample_y <= ROI_Y;
                if (sample_pixel && (ROI_X < ROI_LAST_X))
                    next_sample_x <= ROI_X + SCALE;

                if (s_axis_tlast) begin
                    x_pos <= {X_BITS{1'b0}};
                    y_pos <= {{(Y_BITS-1){1'b0}}, 1'b1};
                end else begin
                    x_pos <= {{(X_BITS-1){1'b0}}, 1'b1};
                    y_pos <= {Y_BITS{1'b0}};
                end
            end else if (s_axis_tlast) begin
                x_pos <= {X_BITS{1'b0}};
                next_sample_x <= ROI_X;

                if (y_pos == IN_HEIGHT - 1) begin
                    y_pos <= {Y_BITS{1'b0}};
                    next_sample_y <= ROI_Y;
                end else begin
                    y_pos <= y_pos + 1'b1;
                    if ((pixel_y == next_sample_y) && (pixel_y < ROI_LAST_Y))
                        next_sample_y <= next_sample_y + SCALE;
                end
            end else begin
                x_pos <= x_pos + 1'b1;
                if (sample_pixel && (pixel_x < ROI_LAST_X))
                    next_sample_x <= next_sample_x + SCALE;
            end
        end
    end
end

endmodule
