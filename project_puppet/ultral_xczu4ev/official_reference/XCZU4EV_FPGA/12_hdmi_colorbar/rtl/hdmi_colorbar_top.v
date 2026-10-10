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
// File name:           hdmi_colorbar_top
// Last modified Date:  2021/10/28 09:40:24
// Last Version:        V1.1
// Descriptions:        HDMI彩条显示实验顶层模块
//----------------------------------------------------------------------------------------
// Created by:          正点原子
// Created date:        2021/10/28 09:40:24
// Version:             V1.0
// Descriptions:        The original version
//
//----------------------------------------------------------------------------------------
//****************************************************************************************//

module  hdmi_colorbar_top(
    input        sys_clk_p,
    input        sys_clk_n,
    input        sys_rst_n,
    
    output       tmds_clk_p,    // TMDS 时钟通道
    output       tmds_clk_n,
    output [2:0] tmds_data_p,   // TMDS 数据通道
    output [2:0] tmds_data_n
);
//wire define
wire          pixel_clk;
wire          pixel_clk_5x;
wire          pixel_clk_2_5x;
wire          locked;

wire  [10:0]  pixel_xpos_w;
wire  [10:0]  pixel_ypos_w;
wire  [23:0]  pixel_data_w;
wire          video_hs;
wire          video_vs;
wire          video_de;
wire  [23:0]  video_rgb;

wire          rst_n;

//*****************************************************
//**                    main code
//*****************************************************

assign rst_n = sys_rst_n & locked;

//例化MMCM/PLL IP核
clk_wiz_0 u_clk_wiz_0(
    // Clock out ports
    .clk_out1       (pixel_clk),       //pixel_clk  
    .clk_out2       (pixel_clk_5x),    //pixel_clk的5倍时钟   
    .clk_out3       (pixel_clk_2_5x),  //pixel_clk的2.5倍时钟      
    // Status and control signals
    .reset          (~sys_rst_n),     
    .locked         (locked),     
    // Clock in ports
    .clk_in1_p      (sys_clk_p),      
    .clk_in1_n      (sys_clk_n)
);     

//例化视频显示驱动模块
video_driver u_video_driver(
    .pixel_clk      (pixel_clk),
    .sys_rst_n      (rst_n),

    .video_hs       (video_hs),
    .video_vs       (video_vs),
    .video_de       (video_de),
    .video_rgb      (video_rgb),

    .pixel_xpos     (pixel_xpos_w),
    .pixel_ypos     (pixel_ypos_w),
    .pixel_data     (pixel_data_w)
);

//例化视频显示模块
video_display  u_video_display(
    .pixel_clk      (pixel_clk),
    .sys_rst_n      (rst_n),

    .pixel_xpos     (pixel_xpos_w),
    .pixel_ypos     (pixel_ypos_w),
    .pixel_data     (pixel_data_w)
);

//例化HDMI驱动模块
dvi_transmitter_top u_rgb2dvi_0(
    .pclk           (pixel_clk),
    .pixel_clk_5x   (pixel_clk_5x),
    .pixel_clk_2_5x (pixel_clk_2_5x),
    .reset_n        (rst_n),
                
    .video_din      (video_rgb),
    .video_hsync    (video_hs), 
    .video_vsync    (video_vs),
    .video_de       (video_de),
                
    .tmds_clk_p     (tmds_clk_p),
    .tmds_clk_n     (tmds_clk_n),
    .tmds_data_p    (tmds_data_p),
    .tmds_data_n    (tmds_data_n), 
    .tmds_oen       ()                        //预留的端口，本次实验未用到
    );

endmodule 