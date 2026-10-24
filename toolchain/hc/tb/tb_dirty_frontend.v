/* Modified for v1.0.0: normalized public identifiers and technical documentation. */
`timescale 1ns/1ps
module tb_dirty_frontend;
 reg clk=0;
 always #5 clk=~clk;
 reg rst_n=0, observation_change_async=0, observation_dirty_ack=0;
 wire observation_dirty_latched;
 wcm_sticky_change_frontend dut (.*);
 initial begin
   @(negedge clk); rst_n=1;
   #1; observation_change_async=1;
   #1; if (observation_dirty_latched !== 1'b1) $fatal(1,"missed async change");
   #1; observation_change_async=0;
   #1; if (observation_dirty_latched !== 1'b1) $fatal(1,"change lost before ack");
   @(negedge clk); observation_dirty_ack=1;
   @(posedge clk); #1;
   if (observation_dirty_latched !== 1'b0) $fatal(1,"ack did not clear");
   @(negedge clk); observation_dirty_ack=0;
   #1; observation_change_async=1;
   #1; if (observation_dirty_latched !== 1'b1) $fatal(1,"new change not sticky");
   #1; observation_change_async=0;
   rst_n=0; #1;
   if (observation_dirty_latched !== 1'b0) $fatal(1,"reset did not clear frontend");
   $display("PASS dirty-front-end handshake experiment"); $finish;
 end
endmodule
