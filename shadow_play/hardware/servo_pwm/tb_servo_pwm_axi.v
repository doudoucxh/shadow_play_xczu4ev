`timescale 1ns/1ps
module tb_servo_pwm_axi;
    parameter integer DIVIDER=1;
    reg clk=0,resetn=0; always #5 clk=~clk;
    reg [11:0] awaddr=0,araddr=0;
    reg [31:0] wdata=0;reg [3:0] wstrb=15;
    reg awvalid=0,wvalid=0,bready=0,arvalid=0,rready=0;
    wire awready,wready,bvalid,arready,rvalid;wire[1:0] bresp,rresp;wire[31:0] rdata;wire[9:0] pwm;
    servo_pwm_axi #(.CLOCK_HZ(1000000*DIVIDER),.WATCHDOG_US(100000)) dut(
        .aclk(clk),.aresetn(resetn),.s_axi_awaddr(awaddr),.s_axi_awprot(3'b0),.s_axi_awvalid(awvalid),.s_axi_awready(awready),
        .s_axi_wdata(wdata),.s_axi_wstrb(wstrb),.s_axi_wvalid(wvalid),.s_axi_wready(wready),.s_axi_bresp(bresp),.s_axi_bvalid(bvalid),.s_axi_bready(bready),
        .s_axi_araddr(araddr),.s_axi_arprot(3'b0),.s_axi_arvalid(arvalid),.s_axi_arready(arready),.s_axi_rdata(rdata),.s_axi_rresp(rresp),.s_axi_rvalid(rvalid),.s_axi_rready(rready),.servo_pwm(pwm));
    task write_reg;
        input [11:0] address;input [31:0] value;input integer gap;input [1:0] expected;
        begin
            fork
                begin
                    if(gap<0) repeat(-gap) @(negedge clk);
                    @(negedge clk);awaddr=address;awvalid=1;
                    @(negedge clk);while(!awready && !dut.aw_hold) @(negedge clk);awvalid=0;
                end
                begin
                    if(gap>0) repeat(gap) @(negedge clk);
                    @(negedge clk);wdata=value;wvalid=1;
                    @(negedge clk);while(!wready && !dut.w_hold) @(negedge clk);wvalid=0;
                end
            join
            while(!bvalid) @(negedge clk);
            if(bresp!==expected) $fatal(1,"write response addr=%h response=%h expected=%h",address,bresp,expected);
            repeat(3) begin @(negedge clk);if(!bvalid || bresp!==expected) $fatal(1,"B backpressure violated");end
            bready=1;@(negedge clk);bready=0;
        end
    endtask
    task read_reg;
        input [11:0] address;input [31:0] expected;
        begin
            @(negedge clk);araddr=address;arvalid=1;
            @(negedge clk);arvalid=0;
            while(!rvalid) @(negedge clk);
            if(rresp!==0 || rdata!==expected) $fatal(1,"read addr=%h value=%h expected=%h",address,rdata,expected);
            repeat(3) begin @(negedge clk);if(!rvalid || rdata!==expected) $fatal(1,"R backpressure violated");end
            rready=1;@(negedge clk);rready=0;
        end
    endtask
    integer count,j;
    initial begin
        repeat(5) @(negedge clk);resetn=1;
        read_reg(0,32'h53503130);read_reg(8,0);
        write_reg(12'h014,1,3,0);write_reg(12'h018,32'h434f4d54,-3,0);read_reg(12'h00c,4);
        if(pwm!==0) $fatal(1,"Unarmed output");
        write_reg(12'h040,1510,4,0);write_reg(12'h044,1600,-4,0);
        write_reg(12'h010,32'h41524d31,0,0);write_reg(12'h018,32'h434f4d54,0,0);
        wait(dut.active_mask==1);@(negedge clk);
        // Start at the next complete PWM frame; count actual high cycles.
        while(dut.phase_us!=0 || dut.divider!=0) @(negedge clk);
        count=0;
        for(j=0;j<20000*DIVIDER;j=j+1) begin
            if(pwm[0]) count=count+1;
            if(pwm[9:1]!==0) $fatal(1,"An unselected servo emitted PWM");
            @(negedge clk);
        end
        if(count!=1510*DIVIDER) $fatal(1,"Wrong pulse width: %d",count);
        read_reg(12'h080,1510);read_reg(12'h020,1);
        write_reg(12'h01c,32'h4b49434b,0,0);
        write_reg(12'h040,1520,0,0);write_reg(12'h018,32'h434f4d54,0,0);
        read_reg(12'h080,1510); // Buffered command cannot shorten an in-progress pulse.
        wait(!dut.pending);read_reg(12'h080,1520);read_reg(12'h020,2);
        write_reg(12'h040,499,0,2);read_reg(12'h00c,1);
        write_reg(12'h018,32'h434f4d54,0,0);read_reg(12'h00c,5);
        write_reg(12'h00c,0,0,0);if(pwm!==0) $fatal(1,"OFF did not gate the outputs");
        write_reg(12'h010,32'h41524d31,0,0);write_reg(12'h014,1023,0,0);
        write_reg(12'h018,32'h434f4d54,0,0);wait(dut.active_mask==1023);
        repeat(100100*DIVIDER) @(negedge clk);
        read_reg(8,0);read_reg(12'h010,0);read_reg(12'h00c,2);
        write_reg(12'h01c,32'h4b49434b,0,0);read_reg(12'h010,0);read_reg(12'h00c,2);
        write_reg(12'h018,32'h434f4d54,0,0);read_reg(12'h010,0);read_reg(12'h00c,6);
        if(pwm!==0) $fatal(1,"Watchdog did not gate outputs");
        $display("PASS: reset off, ARM gate, ten channels, split AXI writes, response backpressure, 20ms/1510us pulse, atomic frame commit, range rejection, OFF, watchdog");
        $finish;
    end
    initial begin #(5000000*DIVIDER);$fatal(1,"Test timeout");end
endmodule
module tb_servo_pwm_100mhz;
    tb_servo_pwm_axi #(.DIVIDER(100)) test();
endmodule
