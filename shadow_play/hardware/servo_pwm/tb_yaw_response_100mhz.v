`timescale 1ns/1ps
// Offline regression for the observed 1st-axis command/rotation discrepancy.
// Measure physical output edges at 100 MHz; active-register reads alone are
// deliberately insufficient. This simulation never accesses the real board.
module tb_yaw_response_100mhz;
    reg clk=0, resetn=0; always #5 clk=~clk;
    reg [11:0] awaddr=0, araddr=0;
    reg [31:0] wdata=0;
    reg awvalid=0,wvalid=0,bready=0,arvalid=0,rready=0;
    wire awready,wready,bvalid,arready,rvalid;
    wire [1:0] bresp,rresp; wire [31:0] rdata; wire [9:0] pwm;
    integer sequence=0, target=1537, i;
    time last_yaw_rise=0;
    servo_pwm_axi dut(.aclk(clk),.aresetn(resetn),
        .s_axi_awaddr(awaddr),.s_axi_awprot(3'b0),.s_axi_awvalid(awvalid),.s_axi_awready(awready),
        .s_axi_wdata(wdata),.s_axi_wstrb(4'hf),.s_axi_wvalid(wvalid),.s_axi_wready(wready),
        .s_axi_bresp(bresp),.s_axi_bvalid(bvalid),.s_axi_bready(bready),
        .s_axi_araddr(araddr),.s_axi_arprot(3'b0),.s_axi_arvalid(arvalid),.s_axi_arready(arready),
        .s_axi_rdata(rdata),.s_axi_rresp(rresp),.s_axi_rvalid(rvalid),.s_axi_rready(rready),
        .servo_pwm(pwm));
    task write_reg;
        input [11:0] address; input [31:0] value;
        begin
            @(negedge clk); awaddr=address;wdata=value;awvalid=1;wvalid=1;
            @(negedge clk); awvalid=0;wvalid=0;
            wait(bvalid); if(bresp!==0) $fatal(1,"AXI write rejected");
            @(negedge clk);bready=1;@(negedge clk);bready=0;
        end
    endtask
    reg measuring=0;
    reg [5:0] measured=0;
    function integer expected_width;
        input integer channel;
        begin
            case(channel)
                0:expected_width=target;1:expected_width=1422;2:expected_width=1537;
                3:expected_width=1474;4:expected_width=1508;5:expected_width=1740;
                default:expected_width=0;
            endcase
        end
    endfunction
    genvar channel;
    generate for(channel=0;channel<6;channel=channel+1) begin: measurement
        time start;
        always @(posedge pwm[channel]) if(measuring) begin
            start=$time;
            @(negedge pwm[channel]);
            if($time-start != expected_width(channel)*1000)
                $fatal(1,"ch%0d output pulse %0t, expected %0d us",channel+1,$time-start,expected_width(channel));
            measured[channel]=1;
        end
    end endgenerate
    task check_frame;
        begin
            measured=0;measuring=1;
            wait(measured==63);
            measuring=0;
        end
    endtask
    task update_yaw;
        input integer width_us;
        begin
            target=width_us;
            write_reg(12'h040,width_us);write_reg(12'h018,32'h434f4d54);
            sequence=sequence+1;
            wait(dut.sequence==sequence && !dut.pending);
            if(dut.active[0]!==width_us || dut.active_mask!==63)
                $fatal(1,"Active register/mask mismatch");
            check_frame;
        end
    endtask
    always @(posedge pwm[0]) begin
        if(last_yaw_rise && $time-last_yaw_rise != 20000000)
            $fatal(1,"Extra edge or wrong 20 ms period");
        last_yaw_rise=$time;
    end
    always @(negedge clk) if(resetn && pwm[9:6]!==0) $fatal(1,"Tiger signal enabled");
    initial begin
        repeat(5) @(negedge clk);resetn=1;
        write_reg(12'h044,1422);write_reg(12'h048,1537);write_reg(12'h04c,1474);
        write_reg(12'h050,1508);write_reg(12'h054,1740);
        write_reg(12'h010,32'h41524d31);write_reg(12'h014,63);
        update_yaw(1537);update_yaw(1540);update_yaw(1597);
        update_yaw(1594);update_yaw(1537);
        write_reg(12'h014,0);write_reg(12'h018,32'h434f4d54);
        wait(!dut.pending && dut.active_mask==0);
        write_reg(12'h00c,0);
        repeat(2000000) begin @(negedge clk);if(pwm!==0) $fatal(1,"Output after OFF");end
        $display("PASS: 100 MHz output edges, 1537/1540/1597/1594/1537 us, six-channel hold, 20 ms period, tiger OFF, final OFF");
        $finish;
    end
    initial begin #300000000;$fatal(1,"Test timeout");end
endmodule
