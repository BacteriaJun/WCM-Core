/* Modified for v1.0.0: normalized public identifiers and technical documentation. */
`timescale 1ns/1ps
module tb_wcm_film_p1;
    reg clk=0;
    always #5 clk=~clk;
    reg rst_n=0, power_good=1, hard_fault=0, world_break=0;
    reg observation_dirty_latched=0;
    wire observation_dirty_ack;
    reg timing_alive=1, tx_deadline_ok=1, aero_deadline_ok=1;
    reg capture_w0=0, capture_w1=0, capture_after_cutover=1;
    reg w0_live=1, w1_live=1, energy_sample=0, energy_after_settlement=1;
    reg tx_energy_ok=1, aero_energy_ok=1, req_tx=0, req_aero=0;
    reg local_mission_authorized=1, symbol_done_tick=0, aero_done_pulse=0, aero_done_auth=0;
    reg settle_pulse=0, settle_after_quarantine=1, settled_ok=1;
    reg [7:0] tx_frame=8'b1010_1101;
    wire optical_reflect, tx_active, aero_start, tx_start, actuator_authority, quarantined;
    wire [2:0] state_debug;
    integer i;
    wcm_film_p1 #(.FRAME_BITS(8)) dut (.*);
    task tick; begin @(posedge clk); #1; end endtask
    task settle; begin @(negedge clk); settle_pulse=1; tick(); @(negedge clk); settle_pulse=0; end endtask
    task rebind; begin
        @(negedge clk); capture_w0=1; capture_w1=1; energy_sample=1;
        tick(); @(negedge clk); capture_w0=0; capture_w1=0; energy_sample=0;
        tick();
        if (state_debug != 3'd2) $fatal(1,"not READY after qualified rebind");
    end endtask
    initial begin
        tick(); if (!quarantined) $fatal(1,"reset must quarantine");
        @(negedge clk); rst_n=1;
        settle();
        // Old observations / old energy must not create authority after reset.
        @(negedge clk);
        capture_after_cutover=0; energy_after_settlement=0;
        capture_w0=1; capture_w1=1; energy_sample=1;
        tick();
        @(negedge clk);
        capture_w0=0; capture_w1=0; energy_sample=0;
        capture_after_cutover=1; energy_after_settlement=1;
        tick();
        if (state_debug != 3'd1) $fatal(1,"stale evidence restored authority");
        rebind();
        // Energy and arbitration tests.
        @(negedge clk); req_tx=1; tx_energy_ok=0;
        tick();
        if (state_debug != 3'd2 || tx_start) $fatal(1,"low energy authorized TX");
        @(negedge clk); tx_energy_ok=1; req_aero=1;
        tick();
        if (state_debug != 3'd2 || tx_start || aero_start) $fatal(1,"dual request authorized");
        // Check the start pulse on the edge that grants the request.
        @(negedge clk); req_aero=0; req_tx=1; tick();
        if (!tx_start || !optical_reflect) $fatal(1,"first bit missing");
        @(negedge clk); req_tx=0;
        for (i=0;i<8;i=i+1) begin
            if (optical_reflect !== tx_frame[7-i]) $fatal(1,"bad bit %0d",i);
            symbol_done_tick=1; tick();
            @(negedge clk); symbol_done_tick=0;
        end
        if (tx_active || !quarantined) $fatal(1,"TX must settle after last bit");
        settle(); rebind();
        @(negedge clk); req_aero=1; tick();
        if (!aero_start) $fatal(1,"aero start missing");
        @(negedge clk); req_aero=0; world_break=1; tick();
        if (!quarantined || aero_start) $fatal(1,"break must quarantine");
        @(negedge clk); world_break=0;
        @(negedge clk); capture_w0=1; capture_w1=1; energy_sample=1;
        tick();
        if (!quarantined || actuator_authority) $fatal(1,"quarantine bypass");
        @(negedge clk); capture_w0=0; capture_w1=0; energy_sample=0;
        settle(); rebind();
        // Combinational hard fault masks outputs without another clock.
        @(negedge clk); req_tx=1; tick();
        @(negedge clk); req_tx=0;
        if (!optical_reflect) $fatal(1,"expected high optical symbol");
        // A persistent asynchronous change must invalidate authority even
        // strictly between clock edges; capture front-end holds until ack.
        observation_dirty_latched=1; #1;
        if (optical_reflect || actuator_authority || !quarantined || !observation_dirty_ack)
            $fatal(1,"dirty evidence did not asynchronously revoke control");
        observation_dirty_latched=0; #1;
        if (!quarantined || actuator_authority)
            $fatal(1,"dirty evidence allowed old authority resurrection");
        // Separately test brownout asynchronous assertion after fresh rebind.
        settle(); rebind();
        @(negedge clk); req_tx=1; tick();
        @(negedge clk); req_tx=0;
        hard_fault=1; #1;
        if (optical_reflect || actuator_authority || !quarantined)
            $fatal(1,"asynchronous fault reset failed");
        // Short fault ends before any clock edge: state must stay quarantined.
        hard_fault=0; #1;
        if (!quarantined) $fatal(1,"fault state resurrected after pulse");
        tick(); if (!quarantined) $fatal(1,"fault quarantine failed");
        $display("PASS WCM-Film P2 RTL testbench"); $finish;
    end
endmodule
