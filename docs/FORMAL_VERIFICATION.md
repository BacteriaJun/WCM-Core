# Formal specification checks

The verification suite evaluates 32 QF_BV SMT queries using Z3. It covers
handwritten finite specifications of the Mission-64 format, serial loader,
mission policy, transaction accounting and timer overflow.

## Reproduction

```sh
make formal-check
python3 verification/formal/prove.py
z3 -smt2 verification/formal/smt2/CRC_RTL_BYTEWISE_EQUIV.smt2
```

Install the Z3 command-line tool or a native library accessible through Python
`ctypes`. Queries are stored in `verification/formal/smt2/`; solver outcomes
and query hashes are in `verification/reports/formal_results.json`.
Source pins record the implementation files associated with the model review.

## Coverage

| Model | Checked property |
|---|---|
| CRC recurrence | Bitwise and bytewise algorithms agree for every 56-bit payload |
| Mission acceptance | Encoded acceptance predicates agree for arbitrary 64-bit images |
| Corruption detection | Every single-bit change to an accepted image is detected |
| Serial loader | Reset, 64-bit loading, count saturation and sticky invalidation |
| Mission policy | Commit-qualified counting, report bounds, abort and terminal states |
| Timer | Overflow transitions to failure while preserving count and elapsed bounds |
| Mutation control | Removing settlement qualification produces a SAT counterexample |

The safety-counterexample queries expect 31 UNSAT results. The intentional
mutation expects one SAT result. Separately, HC checks 53 combinational
forbidden-output conditions against generated Verilog assignments.

## Model assumptions

- `nvm_bit_valid` represents a sampled storage bit in MSB-first order.
- The loader's `candidate_ok` input abstracts CRC and field checking, covered
  separately by the acceptance predicates.
- `due` is arbitrary in the policy model; sampling and physical time accuracy
  are handled by the implementation and target timebase.
- `commit` requires a started frame, eight closed symbols, quarantine,
  transaction-specific settlement, valid power/reset, and clear fault inputs.
- `max_reports` is 1..63. Active states hold a count below the maximum;
  passive completion holds a count equal to the maximum.
- Sensor evidence, clock, power, storage and settlement signals depend on
  target-specific frontend qualification.

## State behavior

Report count advances after qualified commit in `INFLIGHT`. Abort, dirty
evidence and World Break hold the count. `FAILED` persists until reset.
`PASSIVE` persists unless a later fault changes it to `FAILED`.

The serial loader accepts a mission after all 64 bits arrive. Further bits
invalidate an accepted image; cold reset clears loader state.

`MUTATION_MISSING_SETTLEMENT_IS_DETECTED` deliberately uses acceptance in
place of settlement-qualified completion. Its SAT model confirms that the
query detects this faulty count-update rule.

## Implementation evidence

These results apply to the specified mathematical models. Correspondence with
the complete RTL, asynchronous timing, clock-domain crossing and electrical
behavior requires separate implementation and hardware checks.

`make film-rtl-test` supplies a serial-loader bench and complete endpoint
elaboration. `make hc-rtl-test` exercises generated control traces.
`make film-synth` supplies generic synthesis. Their executed status is recorded
in `docs/VALIDATION_1_0_0.md`.
