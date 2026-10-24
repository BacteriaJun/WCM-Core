/* Modified for v1.0.0: normalized public identifiers and technical documentation. */
// WCM-Core: no-CPU Mission-64 serial NVM loader and local policy.
// Target frontends provide the serial storage source, 1ms timebase, sensor,
// reset and power-good signals. Task intents pass through the Film Commit gate.
// Ordering: most significant image bit (bit 63) first, CRC8 as the final byte.
// Verilog-2005 source for target-specific synthesis.
module wcm_mission64_engine (
    input wire clk, rst_n, power_good, hard_fault, timing_alive,
    input wire nvm_bit_valid, nvm_bit,
    input wire tick_1ms,
    input wire sensor_valid,
    input wire [15:0] sensor_value,
    input wire tx_accept,       // authoritative WCM-Film TX start
    input wire tx_complete,     // externally qualified PHY settlement for THIS TX
    input wire tx_abort,        // any failed/incomplete transaction
    output wire mission_valid,
    output wire mission_bad,
    output wire mission_complete,
    output wire local_policy_authorized,
    output wire req_tx,
    output wire [7:0] tx_frame,
    output wire [5:0] reports_done,
    output wire [2:0] policy_state
);
    localparam [2:0] P_LOAD=3'd0, P_ACTIVE=3'd1, P_REQUEST=3'd2,
                     P_INFLIGHT=3'd3, P_PASSIVE=3'd4, P_FAILED=3'd5;
    wire reset_ok = rst_n && power_good && !hard_fault && timing_alive;
    reg [63:0] bits;
    reg [5:0] nvm_count;
    reg verified, invalid;
    reg [2:0] state;
    reg [5:0] completed;
    reg [15:0] elapsed_ms, last_report_ms;
    reg [5:0] sample_phase;
    reg sampled, sensor_met;

    function [7:0] crc8_atm;
        input [55:0] payload;
        reg [7:0] crc;
        integer i;
        begin
            crc=8'h00;
            for(i=55;i>=0;i=i-1) begin
                // MSB-first CRC-8/ATM: poly 0x07, init 0, xorout 0.
                crc={crc[6:0],1'b0} ^ ((crc[7]^payload[i]) ? 8'h07 : 8'h00);
            end
            crc8_atm=crc;
        end
    endfunction
    wire [63:0] candidate={bits[62:0],nvm_bit};
    wire [3:0] mission_task=bits[59:56];
    wire [5:0] threshold=bits[51:46];
    wire [5:0] sample_period=bits[45:40];
    wire [5:0] report_period=bits[39:34];
    wire [5:0] max_reports=bits[33:28];
    wire [11:0] seed=bits[27:16];
    wire candidate_ok = (candidate[63:60] == 4'd1) &&
        ((candidate[59:56] == 4'd1 && candidate[51:46] != 6'd0) ||
         (candidate[59:56] == 4'd2 && candidate[51:46] == 6'd0)) &&
        candidate[55:52] == 4'd1 && candidate[45:40] != 6'd0 &&
        candidate[39:34] != 6'd0 && candidate[33:28] != 6'd0 &&
        candidate[15:8] == 8'd0 &&
        crc8_atm(candidate[63:8]) == candidate[7:0];
    assign mission_valid = reset_ok && verified && !invalid;
    assign mission_bad = reset_ok && invalid;
    assign policy_state=state;
    assign reports_done=completed;
    assign mission_complete=mission_valid && state==P_PASSIVE;
    assign local_policy_authorized=mission_valid &&
        (state==P_ACTIVE || state==P_REQUEST || state==P_INFLIGHT);
    assign req_tx=local_policy_authorized && state==P_REQUEST;
    assign tx_frame=8'hA0 | {4'd0,completed[3:0]};

    // Missed NVM symbols keep loader closed indefinitely; bad or extra symbols
    // fail closed. No updates are permitted after verification until cold reset.
    always @(posedge clk or negedge reset_ok) begin
        if(!reset_ok) begin
            bits<=64'd0; nvm_count<=6'd0;
            verified<=1'b0; invalid<=1'b0;
        end else if(nvm_bit_valid && !invalid) begin
            if(verified) begin
                invalid<=1'b1; verified<=1'b0;
            end else if(nvm_count==6'd63) begin
                bits<=candidate;
                verified<=candidate_ok;
                invalid<=!candidate_ok;
            end else begin
                bits<=candidate;
                nvm_count<=nvm_count+6'd1;
            end
        end
    end

    wire [15:0] threshold_scaled=({10'd0,threshold} << 3) +
                                  ({10'd0,threshold} << 1); // 10*threshold
    wire due = sampled && sensor_met && completed<max_reports &&
      ((completed==0 && elapsed_ms >= {12'd0,seed[3:0]}) ||
       (completed!=0 && elapsed_ms>=last_report_ms &&
        (elapsed_ms-last_report_ms)>= ({6'd0,report_period} * 10)));
    always @(posedge clk or negedge reset_ok) begin
        if(!reset_ok) begin
            state<=P_LOAD; completed<=6'd0;
            elapsed_ms<=16'd0; last_report_ms<=16'd0;
            sample_phase<=6'd0; sampled<=1'b0; sensor_met<=1'b0;
        end else if(invalid || tx_abort) begin
            state<=P_FAILED;
        end else if(state==P_LOAD) begin
            if(verified) state<=P_ACTIVE;
        end else if(state==P_ACTIVE || state==P_REQUEST || state==P_INFLIGHT) begin
            if(tick_1ms) begin
                if(elapsed_ms==16'hffff) state<=P_FAILED; // never wrap scheduling time
                else elapsed_ms<=elapsed_ms+16'd1;
                if(sample_phase==sample_period-6'd1) begin
                    sample_phase<=6'd0;
                    // stale/missing physical sensor evidence cannot authorize work
                    sampled<=sensor_valid;
                    if(sensor_valid) sensor_met <= (mission_task==4'd2) ||
                                                         (sensor_value >= threshold_scaled);
                    else sensor_met<=1'b0;
                end else sample_phase<=sample_phase+6'd1;
            end
            // Overflow quarantine has priority over every action handshake.
            if(tick_1ms && elapsed_ms==16'hffff) state<=P_FAILED;
            else if(state==P_ACTIVE && due) state<=P_REQUEST;
            else if(state==P_REQUEST && tx_accept) state<=P_INFLIGHT;
            else if(state==P_INFLIGHT && tx_complete) begin
                completed<=completed+6'd1;
                last_report_ms<=elapsed_ms;
                sampled<=1'b0; // require fresh local sample for next transaction
                if(completed+6'd1>=max_reports) state<=P_PASSIVE;
                else state<=P_ACTIVE;
            end
        end
    end
endmodule
