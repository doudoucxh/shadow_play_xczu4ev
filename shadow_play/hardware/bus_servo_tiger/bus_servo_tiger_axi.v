`timescale 1ns/1ps
// Four independent tiger buses: ID 7..10 on original connectors 1..4. BT04.
module bus_servo_tiger_axi #(
    parameter integer CLOCK_HZ=100000000,
    parameter integer WATCHDOG_CYCLES=100000000
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
    input wire [3:0] bus_rx,
    output wire [3:0] bus_tx, bus_oe
);
    reg aw_hold,w_hold;
    reg [11:0] address;
    reg [31:0] data;
    reg [3:0] strobes;
    reg [3:0] stage,start,pop,clear_errors;
    reg [7:0] stage_address,stage_data;
    reg [8:0] length;
    reg panic,leased;
    reg [31:0] watchdog,faults;
    wire [3:0] busy;
    wire [7:0] rx_data [0:3];
    wire [8:0] rx_count [0:3];
    wire [2:0] errors [0:3];
    wire any_error = |(errors[0] | errors[1] | errors[2] | errors[3]);
    assign s_axi_awready=!aw_hold && !s_axi_bvalid;
    assign s_axi_wready=!w_hold && !s_axi_bvalid;
    assign s_axi_arready=!s_axi_rvalid;
    genvar channel;
    generate for(channel=0; channel<4; channel=channel+1) begin: uart
        single_wire_uart #(.CLOCK_HZ(CLOCK_HZ)) engine(
            .clk(aclk),.resetn(aresetn),.rx(bus_rx[channel]),.tx(bus_tx[channel]),.oe(bus_oe[channel]),
            .stage(stage[channel]),.stage_address(stage_address),.stage_data(stage_data),
            .start(start[channel]),.length(length),.panic(panic),.pop(pop[channel]),
            .clear_errors(clear_errors[channel]),.rx_data(rx_data[channel]),.rx_count(rx_count[channel]),
            .busy(busy[channel]),.errors(errors[channel]));
    end endgenerate
    always @(posedge aclk) begin
        if(!aresetn) begin
            aw_hold<=0;w_hold<=0;address<=0;data<=0;strobes<=0;
            s_axi_bvalid<=0;s_axi_bresp<=0;s_axi_rvalid<=0;s_axi_rresp<=0;s_axi_rdata<=0;
            stage<=0;start<=0;pop<=0;clear_errors<=0;stage_address<=0;stage_data<=0;length<=0;
            panic<=0;leased<=0;watchdog<=0;faults<=0;
        end else begin
            stage<=0;start<=0;pop<=0;clear_errors<=0;panic<=0;
            if(leased && watchdog<WATCHDOG_CYCLES) watchdog<=watchdog+1;
            if(s_axi_bvalid && s_axi_bready) s_axi_bvalid<=0;
            if(s_axi_awvalid && s_axi_awready) begin aw_hold<=1;address<=s_axi_awaddr;end
            if(s_axi_wvalid && s_axi_wready) begin w_hold<=1;data<=s_axi_wdata;strobes<=s_axi_wstrb;end
            if(aw_hold && w_hold && !s_axi_bvalid) begin
                aw_hold<=0;w_hold<=0;s_axi_bvalid<=1;s_axi_bresp<=0;
                if(strobes!=4'hf || address[1:0]!=0) s_axi_bresp<=2;
                else case(address)
                    12'h00c: if(data==32'h53544f50) begin panic<=1;leased<=0;end else s_axi_bresp<=2;
                    // Explicit fresh motion lease; never issued by heartbeat or read.
                    12'h010: if(data==32'h41524d31 && !leased && busy==0 && !any_error && faults==0)
                        begin leased<=1;watchdog<=0;end else s_axi_bresp<=2;
                    12'h014: if(data==32'h4b49434b) begin if(leased) watchdog<=0;end else s_axi_bresp<=2;
                    // Error reset is an explicit commissioning action, absent from normal host GUI.
                    12'h020: if(data==32'h434c5231 && !leased && busy==0) begin faults<=0;clear_errors<=15;end else s_axi_bresp<=2;
                    12'h108: begin
                        if(faults!=0 || busy[0] || data>65535) s_axi_bresp<=2;
                        else begin stage[0]<=1;stage_address<=data[15:8];stage_data<=data[7:0];end
                    end
                    12'h10c: begin
                        if(faults!=0 || busy[0] || data==0 || data>256) s_axi_bresp<=2;
                        else begin start[0]<=1;length<=data[8:0];end
                    end
                    12'h208: begin
                        if(faults!=0 || busy[1] || data>65535) s_axi_bresp<=2;
                        else begin stage[1]<=1;stage_address<=data[15:8];stage_data<=data[7:0];end
                    end
                    12'h20c: begin
                        if(faults!=0 || busy[1] || data==0 || data>256) s_axi_bresp<=2;
                        else begin start[1]<=1;length<=data[8:0];end
                    end
                    12'h308: begin
                        if(faults!=0 || busy[2] || data>65535) s_axi_bresp<=2;
                        else begin stage[2]<=1;stage_address<=data[15:8];stage_data<=data[7:0];end
                    end
                    12'h30c: begin
                        if(faults!=0 || busy[2] || data==0 || data>256) s_axi_bresp<=2;
                        else begin start[2]<=1;length<=data[8:0];end
                    end
                    12'h408: begin
                        if(faults!=0 || busy[3] || data>65535) s_axi_bresp<=2;
                        else begin stage[3]<=1;stage_address<=data[15:8];stage_data<=data[7:0];end
                    end
                    12'h40c: begin
                        if(faults!=0 || busy[3] || data==0 || data>256) s_axi_bresp<=2;
                        else begin start[3]<=1;length<=data[8:0];end
                    end
                    default:s_axi_bresp<=2;
                endcase
            end
            // Expiration wins over a simultaneous late heartbeat/GO.
            if(leased && (watchdog>=WATCHDOG_CYCLES || any_error)) begin
                leased<=0;panic<=1;start<=0;stage<=0;faults<=watchdog>=WATCHDOG_CYCLES ? 1 : 2;
            end
            if(s_axi_rvalid && s_axi_rready) s_axi_rvalid<=0;
            if(s_axi_arvalid && s_axi_arready) begin
                s_axi_rvalid<=1;s_axi_rresp<=0;s_axi_rdata<=0;
                case(s_axi_araddr)
                    12'h000:s_axi_rdata<=32'h42543034;
                    12'h004:s_axi_rdata<=1;
                    12'h008:s_axi_rdata<=faults;
                    12'h010:s_axi_rdata<={31'b0,leased};
                    12'h018:s_axi_rdata<=CLOCK_HZ;
                    12'h01c:s_axi_rdata<=115200;
                    12'h024:s_axi_rdata<=4;
                    12'h100:s_axi_rdata<={5'b0,errors[0],7'b0,rx_count[0],7'b0,busy[0]};
                    12'h104:if(rx_count[0]!=0) begin s_axi_rdata<={24'b0,rx_data[0]};pop[0]<=1;end else s_axi_rresp<=2;
                    12'h200:s_axi_rdata<={5'b0,errors[1],7'b0,rx_count[1],7'b0,busy[1]};
                    12'h204:if(rx_count[1]!=0) begin s_axi_rdata<={24'b0,rx_data[1]};pop[1]<=1;end else s_axi_rresp<=2;
                    12'h300:s_axi_rdata<={5'b0,errors[2],7'b0,rx_count[2],7'b0,busy[2]};
                    12'h304:if(rx_count[2]!=0) begin s_axi_rdata<={24'b0,rx_data[2]};pop[2]<=1;end else s_axi_rresp<=2;
                    12'h400:s_axi_rdata<={5'b0,errors[3],7'b0,rx_count[3],7'b0,busy[3]};
                    12'h404:if(rx_count[3]!=0) begin s_axi_rdata<={24'b0,rx_data[3]};pop[3]<=1;end else s_axi_rresp<=2;
                    default:s_axi_rresp<=2;
                endcase
            end
        end
    end
endmodule
