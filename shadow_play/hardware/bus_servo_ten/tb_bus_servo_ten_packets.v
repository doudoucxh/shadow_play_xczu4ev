`timescale 1ns/1ps
// Full addressed query frames at the production clock/baud.
module tb_bus_servo_ten_packets;
    reg clk=0; always #5 clk=~clk;
    reg resetn=0;
    reg [11:0] awaddr=0,araddr=0;
    reg awvalid=0,wvalid=0,arvalid=0;
    wire awready,wready,arready;
    reg [31:0] wdata=0;
    wire [31:0] rdata;
    wire bvalid,rvalid; wire [1:0] bresp,rresp;
    reg [9:0] rx=10'h3ff;
    wire [9:0] tx,oe;
    bus_servo_ten_axi dut(
        .aclk(clk),.aresetn(resetn),.s_axi_awaddr(awaddr),.s_axi_awprot(3'b0),
        .s_axi_awvalid(awvalid),.s_axi_awready(awready),.s_axi_wdata(wdata),
        .s_axi_wstrb(4'hf),.s_axi_wvalid(wvalid),.s_axi_wready(wready),
        .s_axi_bresp(bresp),.s_axi_bvalid(bvalid),.s_axi_bready(1'b1),
        .s_axi_araddr(araddr),.s_axi_arprot(3'b0),.s_axi_arvalid(arvalid),
        .s_axi_arready(arready),.s_axi_rdata(rdata),.s_axi_rresp(rresp),
        .s_axi_rvalid(rvalid),.s_axi_rready(1'b1),.bus_rx(rx),.bus_tx(tx),.bus_oe(oe));
    localparam DIV=868;
    integer port,j,b;
    reg [71:0] request;
    reg [31:0] value;
    reg test_passed=0;
    task automatic write_reg(input [11:0] addr,input [31:0] data);
        begin
            @(negedge clk);awaddr=addr;awvalid=1;wdata=data;wvalid=1;
            // Test simultaneous channels used by the PS, plus the independent
            // channels already covered by tb_bus_servo_ten_axi.
            while(!awready || !wready) @(negedge clk);
            @(negedge clk);awvalid=0;wvalid=0;
            wait(bvalid);
            if(bresp!==0) $fatal(1,"Write rejected %h (%b)",addr,bresp);
            @(negedge clk);
        end
    endtask
    task automatic read_reg(input [11:0] addr,output [31:0] data);
        begin
            @(negedge clk);araddr=addr;arvalid=1;
            while(!arready) @(negedge clk);
            @(negedge clk);arvalid=0;
            wait(rvalid);data=rdata;
            if(rresp!==0) $fatal(1,"Read rejected %h",addr);
            @(negedge clk);
        end
    endtask
    task automatic receive_frame(input integer channel,input [71:0] expected);
        reg [7:0] actual;integer n,k;
        begin
            for(n=0;n<9;n=n+1) begin
                wait(oe[channel] && !tx[channel]);
                repeat(DIV+DIV/2) @(negedge clk);
                for(k=0;k<8;k=k+1) begin actual[k]=tx[channel];repeat(DIV) @(negedge clk);end
                if(tx[channel]!==1 || actual!==expected[71-n*8-:8])
                    $fatal(1,"Port %0d byte %0d got %h expected %h",channel+1,n,actual,expected[71-n*8-:8]);
                repeat(DIV/2) @(negedge clk);
            end
            wait(!oe[channel]);
        end
    endtask
    task automatic send_byte(input integer channel,input [7:0] data);
        integer k;
        begin
            @(negedge clk);rx[channel]=0;repeat(DIV) @(negedge clk);
            for(k=0;k<8;k=k+1) begin rx[channel]=data[k];repeat(DIV) @(negedge clk);end
            rx[channel]=1;repeat(DIV*2) @(negedge clk);
        end
    endtask
    function [71:0] frame(input integer channel);
        begin
            frame="#000PVER!";
            frame[55:48]="0"+(channel+1)/10;
            frame[47:40]="0"+(channel+1)%10;
        end
    endfunction
    initial begin #3000000;$fatal(1,"Packet simulation timed out; OE=%b BVALID=%b",oe,bvalid);end
    initial begin
        // Hold reset before exercising the production-rate UARTs.
        #1000;@(negedge clk);resetn=1;repeat(10) @(negedge clk);
        read_reg(0,value);if(value!==32'h42503130) $fatal(1,"Identity %h",value);
        read_reg(8,value);if(value!==0 || oe!==0) $fatal(1,"Reset state %h OE %b",value,oe);
        for(port=0;port<10;port=port+1) begin
            request=frame(port);
            for(j=0;j<9;j=j+1) write_reg((port+1)*256+8,(j<<8)|request[71-j*8-:8]);
            $display("PACKET_STAGED %0d",port+1);
        end
        fork
            begin
                for(port=0;port<10;port=port+1) begin
                    write_reg((port+1)*256+12,9);
                    $display("PACKET_STARTED %0d",port+1);
                end
            end
            receive_frame(0,frame(0));receive_frame(1,frame(1));
            receive_frame(2,frame(2));receive_frame(3,frame(3));
            receive_frame(4,frame(4));receive_frame(5,frame(5));
            receive_frame(6,frame(6));receive_frame(7,frame(7));
            receive_frame(8,frame(8));receive_frame(9,frame(9));
        join
        if(oe!==0) $fatal(1,"TX did not release all lines");
        $display("TEN_PORT_TX_PASS");
        for(port=0;port<10;port=port+1) begin
            send_byte(port,"#");send_byte(port,"!");
            read_reg((port+1)*256,value);
            if(value!==32'h200) $fatal(1,"Port %0d RX status %h",port+1,value);
            read_reg((port+1)*256+4,value);if(value!=="#") $fatal(1,"RX first byte");
            read_reg((port+1)*256+4,value);if(value!=="!") $fatal(1,"RX second byte");
            $display("PACKET_PORT_PASS %0d",port+1);
        end
        test_passed=1;
        $display("TEN_PORT_PACKETS_PASS");#1;$finish;
    end
endmodule
