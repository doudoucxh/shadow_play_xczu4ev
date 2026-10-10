`timescale 1ns/1ps
// Ten 50 Hz PWM channels. All outputs remain LOW after reset and until an
// explicit ARM + ENABLE + COMMIT. Values are microseconds, not measured angles.
module servo_pwm_axi #(
    parameter integer CLOCK_HZ = 100000000,
    parameter integer WATCHDOG_US = 2000000
)(
    (* X_INTERFACE_PARAMETER = "ASSOCIATED_BUSIF S_AXI, ASSOCIATED_RESET aresetn" *)
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 aclk CLK" *) input wire aclk,
    (* X_INTERFACE_PARAMETER = "POLARITY ACTIVE_LOW" *)
    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 aresetn RST" *) input wire aresetn,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWADDR" *) input wire [11:0] s_axi_awaddr,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWPROT" *) input wire [2:0] s_axi_awprot,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWVALID" *) input wire s_axi_awvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWREADY" *) output wire s_axi_awready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WDATA" *) input wire [31:0] s_axi_wdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WSTRB" *) input wire [3:0] s_axi_wstrb,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WVALID" *) input wire s_axi_wvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WREADY" *) output wire s_axi_wready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI BRESP" *) output reg [1:0] s_axi_bresp,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI BVALID" *) output reg s_axi_bvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI BREADY" *) input wire s_axi_bready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARADDR" *) input wire [11:0] s_axi_araddr,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARPROT" *) input wire [2:0] s_axi_arprot,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARVALID" *) input wire s_axi_arvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARREADY" *) output wire s_axi_arready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RDATA" *) output reg [31:0] s_axi_rdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RRESP" *) output reg [1:0] s_axi_rresp,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RVALID" *) output reg s_axi_rvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RREADY" *) input wire s_axi_rready,
    output wire [9:0] servo_pwm
);
    localparam integer DIV = CLOCK_HZ/1000000;
    reg aw_hold, w_hold;
    reg [11:0] address;
    reg [31:0] data;
    reg [3:0] strobes;
    reg [31:0] divider, watchdog, sequence;
    reg [14:0] phase_us;
    reg armed, pending;
    reg [9:0] staged_mask, queued_mask, active_mask;
    reg [11:0] staged [0:9], queued [0:9], active [0:9];
    reg [31:0] faults;
    integer i;
    wire tick = divider == DIV-1;
    assign s_axi_awready = !aw_hold && !s_axi_bvalid;
    assign s_axi_wready = !w_hold && !s_axi_bvalid;
    assign s_axi_arready = !s_axi_rvalid;
    // Register physical outputs: binary-counter/comparator propagation must not
    // create narrow extra edges at the servo connector.
    reg [9:0] output_reg;
    assign servo_pwm = aresetn ? output_reg : 10'b0;
    wire explicit_off = aw_hold && w_hold && !s_axi_bvalid &&
                        strobes==4'hf && address==12'h00c && data==0;
    integer output_index;
    always @(posedge aclk) begin
        if(!aresetn || explicit_off || !armed || watchdog>=WATCHDOG_US) output_reg<=0;
        else if(tick) begin
            if(phase_us==19999) output_reg<=pending ? queued_mask : active_mask;
            else for(output_index=0;output_index<10;output_index=output_index+1)
                output_reg[output_index]<=active_mask[output_index] && (phase_us+1 < active[output_index]);
        end
    end
    always @(posedge aclk) begin
        if(!aresetn) begin
            aw_hold<=0;w_hold<=0;s_axi_bvalid<=0;s_axi_bresp<=0;s_axi_rvalid<=0;s_axi_rresp<=0;s_axi_rdata<=0;
            address<=0;data<=0;strobes<=0;divider<=0;phase_us<=0;watchdog<=0;sequence<=0;
            armed<=0;pending<=0;staged_mask<=0;queued_mask<=0;active_mask<=0;faults<=0;
            for(i=0;i<10;i=i+1) begin staged[i]<=1500;queued[i]<=1500;active[i]<=1500;end
        end else begin
            if(tick) begin
                divider<=0;
                if(phase_us==19999) begin
                    phase_us<=0;
                    if(pending && armed) begin
                        for(i=0;i<10;i=i+1) active[i]<=queued[i];
                        active_mask<=queued_mask;pending<=0;sequence<=sequence+1;
                    end
                end else phase_us<=phase_us+1;
                if(armed && watchdog<WATCHDOG_US) watchdog<=watchdog+1;
            end else divider<=divider+1;
            if(s_axi_bvalid && s_axi_bready) s_axi_bvalid<=0;
            if(s_axi_awvalid && s_axi_awready) begin aw_hold<=1;address<=s_axi_awaddr;end
            if(s_axi_wvalid && s_axi_wready) begin w_hold<=1;data<=s_axi_wdata;strobes<=s_axi_wstrb;end
            if(aw_hold && w_hold && !s_axi_bvalid) begin
                aw_hold<=0;w_hold<=0;s_axi_bvalid<=1;s_axi_bresp<=0;
                if(strobes!=4'hf || address[1:0]!=0) s_axi_bresp<=2;
                else if(address>=12'h040 && address<12'h068) begin
                    if(data>=500 && data<=2500) staged[(address-12'h040)>>2]<=data[11:0];
                    else begin s_axi_bresp<=2;faults[0]<=1;end
                end else case(address)
                    12'h00c: begin // Explicit OFF clears pending updates, without moving to a default angle.
                        if(data==0) begin armed<=0;active_mask<=0;staged_mask<=0;queued_mask<=0;pending<=0;end
                        else s_axi_bresp<=2;
                    end
                    12'h010: begin
                        if(data==32'h41524d31 && !armed && active_mask==0) begin armed<=1;watchdog<=0;faults<=0;end
                        else s_axi_bresp<=2;
                    end
                    12'h014: begin
                        if(data<1024) staged_mask<=data[9:0];else s_axi_bresp<=2;
                    end
                    12'h018: begin
                        if(data==32'h434f4d54 && armed && !pending && faults==0) begin
                            for(i=0;i<10;i=i+1) queued[i]<=staged[i];
                            queued_mask<=staged_mask;pending<=1;watchdog<=0;
                        end else faults[2]<=1; // Reject without a CPU external-abort on a watchdog race.
                    end
                    12'h01c: begin
                        // A late valid heartbeat is harmless and cannot rearm.
                        if(data==32'h4b49434b) begin if(armed) watchdog<=0;end
                        else s_axi_bresp<=2;
                    end
                    default: s_axi_bresp<=2;
                endcase
            end
            // Watchdog wins over any simultaneous command. A fresh ARM is required.
            if(armed && watchdog>=WATCHDOG_US) begin
                armed<=0;active_mask<=0;queued_mask<=0;staged_mask<=0;pending<=0;faults[1]<=1;
            end
            if(s_axi_rvalid && s_axi_rready) s_axi_rvalid<=0;
            if(s_axi_arvalid && s_axi_arready) begin
                s_axi_rvalid<=1;s_axi_rresp<=0;s_axi_rdata<=0;
                if(s_axi_araddr[1:0]!=0) s_axi_rresp<=2;
                else if(s_axi_araddr>=12'h040 && s_axi_araddr<12'h068) s_axi_rdata<={20'b0,staged[(s_axi_araddr-12'h040)>>2]};
                else if(s_axi_araddr>=12'h080 && s_axi_araddr<12'h0a8) s_axi_rdata<={20'b0,active[(s_axi_araddr-12'h080)>>2]};
                else case(s_axi_araddr)
                    12'h000: s_axi_rdata<=32'h53503130; // SP10
                    12'h004: s_axi_rdata<=1;
                    12'h008: s_axi_rdata<={22'b0,active_mask};
                    12'h00c: s_axi_rdata<=faults;
                    12'h010: s_axi_rdata<={31'b0,armed};
                    12'h014: s_axi_rdata<={22'b0,staged_mask};
                    12'h020: s_axi_rdata<=sequence;
                    12'h024: s_axi_rdata<={31'b0,pending};
                    12'h028: s_axi_rdata<=20000;
                    12'h02c: s_axi_rdata<=CLOCK_HZ;
                    default: s_axi_rresp<=2;
                endcase
            end
        end
    end
endmodule
