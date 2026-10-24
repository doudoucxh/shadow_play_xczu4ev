`timescale 1ns/1ps
// Buffered 115200 8N1 half-duplex engine. OE is low for the complete receive
// interval. No idle push-pull high on a shared servo wire. External electrical
// compatibility must be established; FPGA pins are NOT 5-V tolerant.
module single_wire_uart #(
    parameter integer CLOCK_HZ=100000000,
    parameter integer BAUD=115200
)(
    input wire clk, resetn,
    input wire rx,
    output reg tx, output reg oe,
    input wire stage, input wire [7:0] stage_address, stage_data,
    input wire start, input wire [8:0] length,
    input wire panic,
    input wire pop, clear_errors,
    output wire [7:0] rx_data,
    output wire [8:0] rx_count,
    output wire busy,
    output reg [2:0] errors
);
    localparam integer DIV=(CLOCK_HZ+BAUD/2)/BAUD;
    reg [7:0] memory[0:255];
    reg [7:0] fifo[0:255];
    reg [7:0] rd,wr;
    assign rx_count={1'b0,wr-rd};
    assign rx_data=fifo[rd];
    reg [31:0] tx_clock, rx_clock;
    reg [3:0] tx_bit,rx_bit;
    reg [9:0] shift;
    reg [7:0] received;
    reg [8:0] index, size;
    reg sending, emergency, guard, receiving;
    reg rx_sync1,rx_sync2;
    assign busy=sending || guard;
    function [7:0] stop_byte;
        input [8:0] n;
        begin
            case(n)
                0:stop_byte="#";1:stop_byte="2";2:stop_byte="5";
                3:stop_byte="5";4:stop_byte="P";5:stop_byte="U";
                6:stop_byte="L";7:stop_byte="K";default:stop_byte="!";
            endcase
        end
    endfunction
    always @(posedge clk) begin
        if(!resetn) begin
            rx_sync1<=1;rx_sync2<=1;
        end else begin rx_sync1<=rx;rx_sync2<=rx_sync1;end
    end
    always @(posedge clk) begin
        if(!resetn) begin
            tx<=1;oe<=0;tx_clock<=0;tx_bit<=0;shift<=10'h3ff;
            index<=0;size<=0;sending<=0;emergency<=0;guard<=0;
            rx_clock<=0;rx_bit<=0;received<=0;receiving<=0;
            rd<=0;wr<=0;errors<=0;
        end else begin
            if(clear_errors) errors<=0;
            if(stage && !busy) memory[stage_address]<=stage_data;
            if(pop && wr!=rd) rd<=rd+1;
            if(panic) begin
                // Break any partial command, wait a whole UART character, then
                // restart with '#' and issue exactly one release per bus.
                sending<=0;oe<=0;tx<=1;guard<=1;emergency<=1;
                tx_clock<=DIV*10-1;index<=0;size<=9;receiving<=0;
            end else if(guard) begin
                if(tx_clock!=0) tx_clock<=tx_clock-1;
                else begin
                    guard<=0;sending<=1;oe<=1;tx<=0;tx_bit<=0;
                    shift<={1'b1,stop_byte(0),1'b0};tx_clock<=DIV-1;
                end
            end else if(start) begin
                if(busy || length==0 || length>256) errors[2]<=1;
                else begin
                    sending<=1;emergency<=0;index<=0;size<=length;
                    oe<=1;tx<=0;tx_bit<=0;shift<={1'b1,memory[0],1'b0};tx_clock<=DIV-1;
                    receiving<=0;
                end
            end else if(sending) begin
                if(tx_clock!=0) tx_clock<=tx_clock-1;
                else if(tx_bit==9) begin
                    if(index+1>=size) begin sending<=0;oe<=0;tx<=1;end
                    else begin
                        index<=index+1;tx_bit<=0;tx<=0;tx_clock<=DIV-1;
                        shift<={1'b1,(emergency ? stop_byte(index+1) : memory[index+1]),1'b0};
                    end
                end else begin
                    tx_bit<=tx_bit+1;shift<={1'b1,shift[9:1]};tx<=shift[1];tx_clock<=DIV-1;
                end
            end
            if(!oe && !guard && !panic && !start) begin
                if(!receiving) begin
                    if(!rx_sync2) begin receiving<=1;rx_clock<=DIV/2-1;rx_bit<=0;end
                end else if(rx_clock!=0) rx_clock<=rx_clock-1;
                else begin
                    rx_clock<=DIV-1;
                    if(rx_bit==0) begin
                        if(rx_sync2) receiving<=0;
                        else rx_bit<=1;
                    end else if(rx_bit<=8) begin
                        received[rx_bit-1]<=rx_sync2;rx_bit<=rx_bit+1;
                    end else begin
                        receiving<=0;
                        if(!rx_sync2) errors[0]<=1;
                        else if((wr+8'd1)==rd) errors[1]<=1;
                        else begin fifo[wr]<=received;wr<=wr+1;end
                    end
                end
            end else receiving<=0;
        end
    end
endmodule
