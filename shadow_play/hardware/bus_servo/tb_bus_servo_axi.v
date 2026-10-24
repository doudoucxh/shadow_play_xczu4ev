`timescale 1ns/1ps
module tb_bus_servo_axi;
    reg clk=0;always #5 clk=~clk;
    reg resetn=0;
    reg [11:0] awaddr=0,araddr=0;
    reg awvalid=0,wvalid=0,arvalid=0;
    wire awready,wready,arready;
    reg [31:0] wdata=0;
    wire [31:0] rdata;
    wire bvalid,rvalid;wire [1:0] bresp,rresp;
    reg [1:0] rx=3;
    wire [1:0] tx,oe;
    bus_servo_axi #(.CLOCK_HZ(1152000),.WATCHDOG_CYCLES(6000)) dut(
        .aclk(clk),.aresetn(resetn),.s_axi_awaddr(awaddr),.s_axi_awprot(3'b0),
        .s_axi_awvalid(awvalid),.s_axi_awready(awready),.s_axi_wdata(wdata),
        .s_axi_wstrb(4'hf),.s_axi_wvalid(wvalid),.s_axi_wready(wready),
        .s_axi_bresp(bresp),.s_axi_bvalid(bvalid),.s_axi_bready(1'b1),
        .s_axi_araddr(araddr),.s_axi_arprot(3'b0),.s_axi_arvalid(arvalid),
        .s_axi_arready(arready),.s_axi_rdata(rdata),.s_axi_rresp(rresp),
        .s_axi_rvalid(rvalid),.s_axi_rready(1'b1),.bus_rx(rx),.bus_tx(tx),.bus_oe(oe));
    task automatic write_reg;
        input [11:0] addr;input [31:0] value;
        begin
            @(negedge clk);awaddr=addr;awvalid=1;
            while(!awready) @(negedge clk);
            @(negedge clk);awvalid=0;
            // Exercise independent AW/W channels, not only simultaneous beats.
            repeat(2) @(negedge clk);
            wdata=value;wvalid=1;
            while(!wready) @(negedge clk);
            @(negedge clk);wvalid=0;
            wait(bvalid);if(bresp!=0) $fatal(1,"AXI write rejected %h",addr);
            @(negedge clk);
        end
    endtask
    task automatic read_reg;
        input [11:0] addr;output [31:0] value;
        begin
            @(negedge clk);araddr=addr;arvalid=1;
            while(!arready) @(negedge clk);
            @(negedge clk);arvalid=0;
            wait(rvalid);value=rdata;if(rresp!=0) $fatal(1,"AXI read rejected %h",addr);
            @(negedge clk);
        end
    endtask
    task automatic receive_byte;
        input integer bus;input [7:0] expected;
        integer b;reg [7:0] actual;
        begin
            wait(oe[bus] && !tx[bus]);
            repeat(15) @(posedge clk);
            for(b=0;b<8;b=b+1) begin actual[b]=tx[bus];repeat(10) @(posedge clk);end
            if(!tx[bus] || actual!==expected) $fatal(1,"TX byte mismatch got %h expected %h",actual,expected);
            repeat(5) @(posedge clk);
        end
    endtask
    task automatic servo_byte;
        input integer bus;input [7:0] value;input good_stop;
        integer b;
        begin
            @(negedge clk);rx[bus]=0;repeat(10) @(negedge clk);
            for(b=0;b<8;b=b+1) begin rx[bus]=value[b];repeat(10) @(negedge clk);end
            rx[bus]=good_stop;repeat(10) @(negedge clk);rx[bus]=1;repeat(10) @(negedge clk);
        end
    endtask
    task automatic release_frame;
        input integer bus;
        begin
            receive_byte(bus,"#");receive_byte(bus,"2");receive_byte(bus,"5");receive_byte(bus,"5");
            receive_byte(bus,"P");receive_byte(bus,"U");receive_byte(bus,"L");receive_byte(bus,"K");receive_byte(bus,"!");
        end
    endtask
    reg [31:0] result;
    initial begin
        #2000000;$fatal(1,"Simulation timed out");
    end
    initial begin
        repeat(5) @(posedge clk);resetn=1;repeat(5) @(posedge clk);
        if(oe!==0) $fatal(1,"Reset must be high impedance");
        read_reg(0,result);if(result!=32'h42533130) $fatal(1,"Wrong BS10 identity");
        // Read-only transmission does not arm motion watchdog or drive bus 1.
        write_reg(12'h108,32'h00000023);
        write_reg(12'h108,32'h00000121);
        fork
            begin write_reg(12'h10c,2);end
            begin receive_byte(0,"#");receive_byte(0,"!");end
        join
        repeat(10) @(posedge clk);
        if(oe!==0) $fatal(1,"TX failed to release the shared wire");
        read_reg(12'h200,result);if(result!=0) $fatal(1,"Other bus changed");
        servo_byte(0,8'hA5,1);servo_byte(0,8'h5A,1);
        read_reg(12'h100,result);if(((result>>8)&511)!=2) $fatal(1,"RX count wrong");
        read_reg(12'h104,result);if(result!=8'hA5) $fatal(1,"RX first byte wrong");
        read_reg(12'h104,result);if(result!=8'h5A) $fatal(1,"RX second byte wrong");
        // No fake local echo was received while transmitting.
        read_reg(12'h100,result);if(result!=0) $fatal(1,"Unexpected echo or RX residue");
        write_reg(12'h010,32'h41524d31);
        fork
            release_frame(0);
            release_frame(1);
        join
        repeat(20) @(posedge clk);
        read_reg(8,result);if(result!=1) $fatal(1,"Watchdog did not latch");
        read_reg(12'h010,result);if(result!=0) $fatal(1,"Watchdog lease survived");
        write_reg(12'h014,32'h4b49434b);
        read_reg(12'h010,result);if(result!=0) $fatal(1,"Heartbeat rearmed watchdog");
        write_reg(12'h020,32'h434c5231);
        servo_byte(1,8'h31,0);
        read_reg(12'h200,result);if((result>>24)!=1) $fatal(1,"Missing framing error");
        write_reg(12'h020,32'h434c5231);
        fork
            write_reg(12'h00c,32'h53544f50);
            release_frame(0);
            release_frame(1);
        join
        repeat(30) @(posedge clk);if(oe!==0) $fatal(1,"Stop must release both lines after command");
        $display("BUS_SERVO_RTL_PASS: reset, independent AXI, TX/RX, no echo, two-bus isolation, watchdog, late heartbeat, framing fault, stop");
        $finish;
    end
endmodule
