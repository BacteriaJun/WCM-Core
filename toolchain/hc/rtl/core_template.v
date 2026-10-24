/* Modified for v1.0.0: normalized public identifiers and technical documentation. */
// WCM-Film P1: technology-neutral synchronous reference RTL (Verilog-2005).
// Fixed-function control with an externally supplied clock.
// Brownout/fault output masking is asynchronous. The target supplies qualified
// buffers, output drivers and synchronized frontend signals for:
// capture_after_cutover, energy_after_settlement, settle_after_quarantine,
// local_mission_authorized, w0_live, w1_live, aero_done_auth.
module wcm_film_p1 #(
    parameter integer FRAME_BITS = 8,
    parameter integer COUNT_BITS = (FRAME_BITS < 2) ? 1 : $clog2(FRAME_BITS + 1)
) (
    input  wire                    clk,
    input  wire                    rst_n,
    input  wire                    power_good,
    input  wire                    hard_fault,
    input  wire                    timing_alive, // independent qualified timeout/watchdog
    input  wire                    tx_deadline_ok,
    input  wire                    aero_deadline_ok,
    input  wire                    world_break,
    input  wire                    observation_dirty_latched,
    output wire                    observation_dirty_ack,
    input  wire                    capture_w0,
    input  wire                    capture_w1,
    input  wire                    capture_after_cutover,
    input  wire                    w0_live,
    input  wire                    w1_live,
    input  wire                    energy_sample,
    input  wire                    energy_after_settlement,
    input  wire                    tx_energy_ok,
    input  wire                    aero_energy_ok,
    input  wire                    req_tx,
    input  wire                    req_aero,
    input  wire                    local_mission_authorized,
    input  wire [FRAME_BITS-1:0]   tx_frame,
    input  wire                    symbol_done_tick,
    input  wire                    aero_done_pulse,
    input  wire                    aero_done_auth,
    input  wire                    settle_pulse,
    input  wire                    settle_after_quarantine,
    input  wire                    settled_ok,
    output wire                    optical_reflect,
    output wire                    tx_active,
    output wire                    aero_start,
    output wire                    tx_start,
    output wire                    actuator_authority,
    output wire                    quarantined,
    output wire [2:0]              state_debug
);
    localparam [2:0] S_QUARANTINE=3'd0, S_REBIND=3'd1,
                     S_READY=3'd2, S_TX=3'd3, S_AERO=3'd4;
    reg [2:0] state;
    reg w0_seen, w1_seen, energy_armed;
    reg [FRAME_BITS-1:0] frame_shift;
    reg [COUNT_BITS-1:0] tx_bits_completed;
    reg tx_start_r, aero_start_r;

    // Analog-level safety must additionally override physical drivers independent
    // of every RTL clock, latch output and internal driver enable.
    wire live_evidence = w0_seen && w1_seen && w0_live && w1_live &&
                         local_mission_authorized && timing_alive;
    // Asynchronous reset path is REQUIRED to prevent power/timer fault pulses
    // from re-enabling stale state between two clock edges. Fabrication must
    // provide a reset cell with specified pulse width / brownout behavior.
    wire reset_domain_ok = rst_n && power_good && !hard_fault && timing_alive;
    wire hard_enable = reset_domain_ok && !world_break && !observation_dirty_latched;
    // Handshake request to the separately qualified asynchronous event capture.
    // External capture must hold dirty until acknowledgement and guarantee
    // that a new event wins over an ack in the same instant.
    assign observation_dirty_ack = (state == S_QUARANTINE) &&
                                   rst_n && power_good && !hard_fault && timing_alive;
    wire evidence_output_ok = live_evidence && !capture_w0 && !capture_w1;
    assign actuator_authority = hard_enable && evidence_output_ok &&
                                ((state == S_TX && tx_deadline_ok) ||
                                 (state == S_AERO && aero_deadline_ok));
    assign optical_reflect = hard_enable && evidence_output_ok &&
                             (state == S_TX) && tx_deadline_ok && frame_shift[FRAME_BITS-1];
    assign aero_start = hard_enable && evidence_output_ok &&
                        (state == S_AERO) && aero_deadline_ok && aero_start_r;
    assign tx_start = hard_enable && evidence_output_ok &&
                      (state == S_TX) && tx_deadline_ok && tx_start_r;
    assign tx_active = hard_enable && tx_deadline_ok && (state == S_TX);
    assign quarantined = (state == S_QUARANTINE);
    assign state_debug = state;

    always @(posedge clk or negedge reset_domain_ok) begin
        if (!reset_domain_ok) begin
            // Cold start cannot assume a bistable mechanical actuator's pose.
            state <= S_QUARANTINE;
            w0_seen <= 1'b0;
            w1_seen <= 1'b0;
            energy_armed <= 1'b0;
            frame_shift <= {FRAME_BITS{1'b0}};
            tx_bits_completed <= {COUNT_BITS{1'b0}};
            tx_start_r <= 1'b0;
            aero_start_r <= 1'b0;
        end else begin
            tx_start_r <= 1'b0;
            aero_start_r <= 1'b0;
            if (!power_good || hard_fault || !timing_alive) begin
                // Electrical fault makes *all* physical pose assumptions void.
                state <= S_QUARANTINE;
                w0_seen <= 1'b0;
                w1_seen <= 1'b0;
                energy_armed <= 1'b0;
            end else if (world_break) begin
                // A break while a physical transaction is outstanding requires
                // trusted settlement; otherwise ordinary evidence rebind suffices.
                if (state == S_TX || state == S_AERO)
                    state <= S_QUARANTINE;
                else if (state != S_QUARANTINE)
                    state <= S_REBIND;
                w0_seen <= 1'b0;
                w1_seen <= 1'b0;
                energy_armed <= 1'b0;
            end else begin
                case (state)
                    S_QUARANTINE: begin
                        if (settle_pulse && settle_after_quarantine && settled_ok) begin
                            state <= S_REBIND;
                            w0_seen <= 1'b0;
                            w1_seen <= 1'b0;
                            energy_armed <= 1'b0;
                        end
                    end
                    S_REBIND: begin
                        // Once physical-time evidence expires it may not be
                        // resurrected simply by an external `live` level.
                        if (!w0_live) w0_seen <= 1'b0;
                        if (!w1_live) w1_seen <= 1'b0;
                        if (capture_w0 && capture_after_cutover && w0_live) w0_seen <= 1'b1;
                        if (capture_w1 && capture_after_cutover && w1_live) w1_seen <= 1'b1;
                        if (energy_sample && energy_after_settlement) energy_armed <= 1'b1;
                        if (w0_seen && w1_seen && w0_live && w1_live && energy_armed &&
                            !capture_w0 && !capture_w1)
                            state <= S_READY;
                    end
                    S_READY: begin
                        if (!w0_live || !w1_live) begin
                            if (!w0_live) w0_seen <= 1'b0;
                            if (!w1_live) w1_seen <= 1'b0;
                            state <= S_REBIND;
                        end else if (capture_w0 || capture_w1) begin
                            // No commit on the same edge as a new observation.
                            if (capture_w0 && capture_after_cutover) w0_seen <= 1'b1;
                            if (capture_w1 && capture_after_cutover) w1_seen <= 1'b1;
                            state <= S_REBIND;
                        end else if (req_tx && !req_aero && local_mission_authorized &&
                                     live_evidence && energy_armed && tx_energy_ok &&
                                     tx_deadline_ok) begin
                            state <= S_TX;
                            frame_shift <= tx_frame;
                            tx_bits_completed <= {COUNT_BITS{1'b0}};
                            energy_armed <= 1'b0;  // one authorization per meter credit
                            tx_start_r <= 1'b1;
                        end else if (req_aero && !req_tx && local_mission_authorized &&
                                            live_evidence && energy_armed && aero_energy_ok &&
                                            aero_deadline_ok) begin
                            state <= S_AERO;
                            energy_armed <= 1'b0;
                            aero_start_r <= 1'b1;
                        end
                    end
                    S_TX: begin
                        if (!live_evidence || !tx_deadline_ok || capture_w0 || capture_w1) begin
                            // Partial optical frame is an *erasure* at receiver.
                            state <= S_QUARANTINE;
                            w0_seen <= 1'b0;
                            w1_seen <= 1'b0;
                            energy_armed <= 1'b0;
                        end else if (symbol_done_tick) begin
                            // Tick closes *current* symbol. The last bit remains
                            // driven for a full symbol interval until last tick.
                            if (tx_bits_completed == FRAME_BITS-1) begin
                                // Last bit finished, but the optical MEMS may
                                // still be moving. Require physical settlement.
                                state <= S_QUARANTINE;
                                w0_seen <= 1'b0;
                                w1_seen <= 1'b0;
                                energy_armed <= 1'b0;
                                frame_shift <= {FRAME_BITS{1'b0}};
                            end else begin
                                tx_bits_completed <= tx_bits_completed + 1'b1;
                                frame_shift <= frame_shift << 1;
                            end
                        end
                    end
                    S_AERO: begin
                        if (!live_evidence || !aero_deadline_ok || capture_w0 || capture_w1) begin
                            state <= S_QUARANTINE;
                            w0_seen <= 1'b0;
                            w1_seen <= 1'b0;
                            energy_armed <= 1'b0;
                        end else if (aero_done_pulse && aero_done_auth) begin
                            // Valid pose confirmation; new evidence and a new
                            // after-settlement power measurement required.
                            state <= S_REBIND;
                            w0_seen <= 1'b0;
                            w1_seen <= 1'b0;
                            energy_armed <= 1'b0;
                        end
                    end
                    default: begin
                        state <= S_QUARANTINE;
                        w0_seen <= 1'b0;
                        w1_seen <= 1'b0;
                        energy_armed <= 1'b0;
                    end
                endcase
            end
        end
    end
endmodule
