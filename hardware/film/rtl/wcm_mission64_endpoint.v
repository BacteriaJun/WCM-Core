/* Modified for v1.0.0: normalized public identifiers and technical documentation. */
// Fixed-function endpoint with local serial storage and task-derived TX requests.
// Target frontends provide qualified evidence, a 1ms tick, energy readings,
// symbol completion, storage access and transaction settlement.
module wcm_mission64_endpoint (
    input wire clk, rst_n, power_good, hard_fault, timing_alive,
    input wire nvm_bit_valid, nvm_bit,
    input wire tick_1ms, sensor_valid, sensor_capture,
    input wire [15:0] sensor_value,
    input wire capture_after_cutover, w0_live,
    input wire energy_sample, energy_after_settlement, tx_energy_ok,
    input wire tx_deadline_ok, world_break, observation_dirty_latched,
    input wire symbol_done_tick,
    input wire settle_pulse, settle_after_quarantine, settled_ok,
    input wire tx_phy_settled_this_frame,
    output wire optical_reflect, tx_active, tx_start,
    output wire actuator_authority, quarantined,
    output wire observation_dirty_ack,
    output wire mission_valid, mission_bad, mission_complete,
    output wire [5:0] reports_done,
    output wire [2:0] policy_state, core_state
);
    wire policy_request, policy_auth;
    wire [7:0] frame;
    wire reset_ok = rst_n && power_good && !hard_fault && timing_alive;
    wire abort_tx;
    wire commit_tx;
    wire aero_unused;
    reg started;
    reg [3:0] symbols_closed;
    reg complete_frame;
    reg policy_capture_sent;
    // One fresh local-policy Witness per REBIND epoch, never station-originated.
    wire capture_policy = mission_valid && policy_auth &&
       (core_state==3'd1) && !policy_capture_sent;
    always @(posedge clk or negedge reset_ok) begin
        if(!reset_ok) policy_capture_sent<=1'b0;
        else if(core_state!=3'd1) policy_capture_sent<=1'b0;
        else if(capture_policy) policy_capture_sent<=1'b1;
    end

    wcm_mission64_engine mission (
        .clk(clk),.rst_n(rst_n),.power_good(power_good),
        .hard_fault(hard_fault),.timing_alive(timing_alive),
        .nvm_bit_valid(nvm_bit_valid),.nvm_bit(nvm_bit),
        .tick_1ms(tick_1ms),.sensor_valid(sensor_valid),
        .sensor_value(sensor_value),.tx_accept(tx_start),
        .tx_complete(commit_tx),.tx_abort(abort_tx),
        .mission_valid(mission_valid),.mission_bad(mission_bad),
        .mission_complete(mission_complete),.local_policy_authorized(policy_auth),
        .req_tx(policy_request),.tx_frame(frame),
        .reports_done(reports_done),.policy_state(policy_state)
    );
    // Last symbol has closed and target-specific PHY positively verifies
    // THIS transaction has fully settled. Merely entering QUARANTINE is not
    // completion. Never count unverified or interrupted frames.
    assign commit_tx = started && complete_frame && quarantined &&
       tx_phy_settled_this_frame && settle_pulse && settle_after_quarantine &&
       settled_ok && reset_ok && !observation_dirty_latched && !world_break;
    assign abort_tx = started && !commit_tx &&
       (!tx_deadline_ok || !w0_live || world_break || observation_dirty_latched ||
        (quarantined && !complete_frame));
    always @(posedge clk or negedge reset_ok) begin
        if(!reset_ok) begin
            started<=1'b0; symbols_closed<=4'd0; complete_frame<=1'b0;
        end else if(tx_start) begin
            started<=1'b1; symbols_closed<=4'd0; complete_frame<=1'b0;
        end else if(commit_tx || abort_tx) begin
            started<=1'b0; symbols_closed<=4'd0; complete_frame<=1'b0;
        end else if(started && tx_active && symbol_done_tick) begin
            if(symbols_closed==4'd7) complete_frame<=1'b1;
            else symbols_closed<=symbols_closed+4'd1;
        end
    end
    wcm_reference_core core (
       .clk(clk),.rst_n(rst_n),.power_good(power_good),.hard_fault(hard_fault),
       .timing_alive(timing_alive),.tx_deadline_ok(tx_deadline_ok),
       .aero_deadline_ok(1'b0),.world_break(world_break),
       .observation_dirty_latched(observation_dirty_latched),
       .observation_dirty_ack(observation_dirty_ack),
       .capture_w0(sensor_capture),.capture_w1(capture_policy),
       .capture_after_cutover(capture_after_cutover),
       .w0_live(w0_live),.w1_live(mission_valid),
       .energy_sample(energy_sample),.energy_after_settlement(energy_after_settlement),
       .tx_energy_ok(tx_energy_ok),.aero_energy_ok(1'b0),
       .req_tx(policy_request),.req_aero(1'b0),
       .local_mission_authorized(policy_auth),.tx_frame(frame),
       .symbol_done_tick(symbol_done_tick),.aero_done_pulse(1'b0),
       .aero_done_auth(1'b0),.settle_pulse(settle_pulse),
       .settle_after_quarantine(settle_after_quarantine),.settled_ok(settled_ok),
       .optical_reflect(optical_reflect),.tx_active(tx_active),
       .aero_start(aero_unused),.tx_start(tx_start),
       .actuator_authority(actuator_authority),.quarantined(quarantined),
       .state_debug(core_state)
    );
endmodule
