`timescale 1ns / 1ps

// Keep the camera flash output inactive. It remains a real top-level port so
// the board pin is always driven to a defined level.
module camera_flash_off (
    output wire cam_flash
);
assign cam_flash = 1'b0;
endmodule

