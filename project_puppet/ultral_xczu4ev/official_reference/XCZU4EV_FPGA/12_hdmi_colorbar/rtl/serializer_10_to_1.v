`timescale 1ns / 1ps
//****************************************Copyright (c)***********************************//
//原子哥在线教学平台：www.yuanzige.com
//技术支持：www.openedv.com   
//淘宝店铺：http://openedv.taobao.com 
//关注微信公众平台微信号："正点原子"，免费获取ZYNQ & FPGA & STM32 & LINUX资料。
//版权所有，盗版必究。
//Copyright(C) 正点原子 2018-2028
//All rights reserved
//----------------------------------------------------------------------------------------
// File name:           serializer_10_to_1
// Last modified Date:  2021/10/28 09:54:24
// Last Version:        V1.1
// Descriptions:        用于实现10:1并串转换
//----------------------------------------------------------------------------------------
// Created by:          正点原子
// Created date:        2021/10/28 09:54:24
// Version:             V1.0
// Descriptions:        The original version
//
//----------------------------------------------------------------------------------------
//****************************************************************************************//

module serializer_10_to_1(
    input [9:0] paralell_data,   // 10-bit 像素数据
    input       reset,           // 复位信号,高电平有效
    input       paralell_clk,    // pixel_clk (1/10串行传输速率时钟)
    input       pixel_clk_5x,    // pixel_clk的5倍时钟 (1/2串行传输速率时钟)
    input       pixel_clk_2_5x,  // pixel_clk的2.5倍时钟 (1/4串行传输速率时钟) 
    output      serial_data_out  // 输出串行数据
);

//reg define
reg  [3:0]  wr_addr;      // 写地址
reg  [3:0]  rd_addr;      // 读地址
wire [9:0]  rd_curr;      // 当前读数据
reg  [9:2]  rd_last;      // 寄存读到的数据
reg  [2:0]  rd_ctrl_cnt;  // 读控制计数器
reg  [3:0]  tx_data;      // 4bit发送数据 

//*****************************************************
//**                    main code
//***************************************************** 

//RAM写地址,0~15循环计数
always @ (posedge paralell_clk) begin
    if(reset)
        wr_addr <= 4'd0;
    else
        wr_addr <= wr_addr + 1'b1;
end

//寄存读到的数据
always @(posedge pixel_clk_2_5x) begin
    rd_last[9:2] <= rd_curr[9:2];
end

//读控制计数器,将读到的10位数据转成4位数据
always @ (posedge pixel_clk_2_5x) begin
    if(reset) begin
        rd_ctrl_cnt<= 3'd0;
        rd_addr <= 4'd0;
    end
    else begin
        case (rd_ctrl_cnt) 
            3'h0 : begin 
                rd_addr <= rd_addr;
                tx_data <= rd_curr[3:0];
                rd_ctrl_cnt<= rd_ctrl_cnt + 1'b1;
            end
            3'h1 : begin 
                rd_addr <= rd_addr + 1'b1;
                tx_data <= rd_curr[7:4];
                rd_ctrl_cnt<= rd_ctrl_cnt + 1'b1;
            end
            3'h2 : begin 
                rd_addr <= rd_addr;
                tx_data <= {rd_curr[1:0], rd_last[9:8]} ;
                rd_ctrl_cnt<= rd_ctrl_cnt + 1'b1;
            end
            3'h3 : begin 
                rd_addr <= rd_addr + 1'b1;
                tx_data <= rd_curr[5:2];
                rd_ctrl_cnt<= rd_ctrl_cnt + 1'b1;
            end
            3'h4 : begin 
                rd_addr <= rd_addr; 
                tx_data <= rd_last[9:6];
                rd_ctrl_cnt<= 3'h0;
            end              
            default:begin
                rd_ctrl_cnt<= 3'd0;
                rd_addr <= 4'd0;
            end
        endcase
    end
end

//例化10个1位分布式RAM
genvar i;
generate
for (i = 0 ; i <= 10 ; i = i+1) begin : bit
  RAM32X1D mem (
     .D     (paralell_data[i]),
     .WCLK  (paralell_clk),
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
     .DPO   (rd_curr[i]));
end
endgenerate

//4:1 DDR模式下的OSERDESE3
   OSERDESE3 #(
      .DATA_WIDTH            (4),               // 并行数据宽度 (4-8)
      .INIT                  (1'b0),            // OSERDES触发器的初始化值
      .IS_CLKDIV_INVERTED    (1'b0),            //（可选）翻转 CLKDIV
      .IS_CLK_INVERTED       (1'b0),            //（可选）翻转 CLK
      .IS_RST_INVERTED       (1'b0),            //（可选）翻转 RST
      .SIM_DEVICE            ("ULTRASCALE_PLUS")// 设置设备版本 (ULTRASCALE, ULTRASCALE_PLUS, ULTRASCALE_PLUS_ES1, // ULTRASCALE_PLUS_ES2)                           
   )
   OSERDESE3_inst (
      .OQ        (serial_data_out),             // 1-bit 输出: 串行数据输出
      .T_OUT     (),                            // 1-bit 输出: 到IBO的三态控制输出
      .CLK       (pixel_clk_5x),                // 1-bit 输入: 高速时钟
      .CLKDIV    (pixel_clk_2_5x),              // 1-bit 输入: 分频时钟
      .D         ({4'b0,tx_data[3:0]}),         // 4-bit 输入: 并行数据输入
      .RST       (reset),                       // 1-bit 输入: 异步复位
      .T         (1'b0)                         // 1-bit 输入: 来自结构的三态输入
   );

endmodule
