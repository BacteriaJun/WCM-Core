/* Modified for v1.0.0: normalized public identifiers and technical documentation. */
// Research properties for a future SVA-capable simulator/formal tool.
// Requires a separate SVA-capable simulator or formal engine.
// These properties concern only synchronous samples of the public pins.
module wcm_p2_properties (
    input logic clk,
    input logic rst_n,
    input logic power_good,
    input logic hard_fault,
    input logic timing_alive,
    input logic world_break,
    input logic observation_dirty_latched,
    input logic w0_live,
    input logic w1_live,
    input logic local_mission_authorized,
    input logic optical_reflect,
    input logic aero_start,
    input logic tx_start,
    input logic actuator_authority,
    input logic [2:0] state_debug
);
    wire abort_now = !rst_n || !power_good || hard_fault || !timing_alive ||
                     world_break || observation_dirty_latched ||
                     !w0_live || !w1_live || !local_mission_authorized;
    a_abort_masks_output: assert property (@(posedge clk)
        abort_now |-> (!optical_reflect && !aero_start &&
                       !tx_start && !actuator_authority));
    a_never_dual_start: assert property (@(posedge clk)
        !(aero_start && tx_start));
    a_tx_only_in_tx_state: assert property (@(posedge clk)
        tx_start |-> state_debug == 3'd3);
    a_aero_only_in_aero_state: assert property (@(posedge clk)
        aero_start |-> state_debug == 3'd4);
endmodule
