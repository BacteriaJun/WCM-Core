/* Modified for v1.0.0: normalized public identifiers and technical documentation. */
`timescale 1ns/1ps
// Icarus-Verilog bench: independent serial mission vectors with handshake.
module tb_wcm_mission64_engine;
 reg clk=0;always #5 clk=~clk;
 reg rst_n=0,power_good=1,hard_fault=0,timing_alive=1;
 reg nvm_bit_valid=0,nvm_bit=0,tick_1ms=0,sensor_valid=1;
 reg [15:0] sensor_value=100;
 reg tx_accept=0,tx_complete=0,tx_abort=0;
 wire mission_valid,mission_bad,mission_complete,local_policy_authorized,req_tx;
 wire [7:0] tx_frame;wire [5:0] reports_done; wire [2:0] policy_state;
 wcm_mission64_engine dut (.*);
 task cycle;begin @(posedge clk);#1;end endtask
 task push_image;
 input [63:0] data;integer i;
 begin for (i=63;i>=0;i=i-1) begin
     @(negedge clk); nvm_bit_valid=1; nvm_bit=data[i]; cycle();
   end
   @(negedge clk);nvm_bit_valid=0;nvm_bit=0;cycle();
 end endtask
 task tick;
 begin @(negedge clk);tick_1ms=1;cycle();
       @(negedge clk);tick_1ms=0;cycle();end endtask
 task accept;
 begin @(negedge clk);tx_accept=1;cycle();
       @(negedge clk);tx_accept=0;cycle();end endtask
 task finish;
 begin @(negedge clk);tx_complete=1;cycle();
       @(negedge clk);tx_complete=0;cycle();end endtask
 // Golden image produced by independent missionc Python packer:
 localparam [63:0] MISSION=64'h11118104300000f7;
 initial begin
   cycle();rst_n=1;cycle();
   if(mission_valid || req_tx) $fatal(1,"unverified mission authorized");
   push_image(MISSION);
   if(!mission_valid || mission_bad) $fatal(1,"valid mission rejected");
   tick();tick();tick();
   if(!req_tx) $fatal(1,"threshold mission did not request report");
   if(tx_frame!==8'hA0) $fatal(1,"wrong first-frame state");
   accept();
   if(req_tx || reports_done!=0) $fatal(1,"accepted but uncompleted report counted");
   finish();
   if(reports_done!=1 || mission_complete) $fatal(1,"first frame settlement failed");
   for(integer j=0;j<11;j=j+1) tick();
   if(!req_tx) $fatal(1,"second frame not scheduled");
   accept();finish();
   if(reports_done!=2) $fatal(1,"second frame not committed");
   for(integer k=0;k<11;k=k+1) tick();
   if(!req_tx) $fatal(1,"third frame not scheduled");
   accept();finish();
   if(!mission_complete || req_tx || reports_done!=3) $fatal(1,"passive terminal failure");
   // Extra OTP bits may NOT silently alter an already verified mission.
   @(negedge clk);nvm_bit_valid=1;nvm_bit=1;cycle();
   if(mission_valid || !mission_bad || req_tx) $fatal(1,"extra NVM bits accepted");
   @(negedge clk);nvm_bit_valid=0;rst_n=0;cycle();
   if(mission_valid || req_tx) $fatal(1,"reset retained authority");
   @(negedge clk);rst_n=1;cycle();
   push_image(MISSION ^ 64'h0000000000000001);
   if(mission_valid || !mission_bad || req_tx) $fatal(1,"CRC mutation accepted");
   $display("PASS: Mission-64 serial loader, 3 settled TXs, passive, extra-data, reset, CRC");
   $finish;
 end
endmodule
