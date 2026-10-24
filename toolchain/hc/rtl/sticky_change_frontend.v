/* Modified for v1.0.0: normalized public identifiers and technical documentation. */
// RESEARCH-ONLY asynchronous event-capture sketch, not target-process-qualified.
// Requires a cell/process supporting asynchronous SET and CLEAR;
// the external event must meet the technology's minimum set pulse width.
// In a simultaneous event and acknowledgement, the event must win.
// A deasserted rst_n discards this token; the core separately cold-starts
// in QUARANTINE and demands trusted physical settlement plus fresh evidence.
module wcm_sticky_change_frontend (
    input  wire clk,
    input  wire rst_n,
    input  wire observation_change_async,
    input  wire observation_dirty_ack,
    output reg  observation_dirty_latched
);
    always @(posedge clk or posedge observation_change_async or negedge rst_n) begin
        if (!rst_n)
            observation_dirty_latched <= 1'b0;
        else if (observation_change_async)
            observation_dirty_latched <= 1'b1; // event priority
        else if (observation_dirty_ack)
            observation_dirty_latched <= 1'b0;
    end
endmodule
