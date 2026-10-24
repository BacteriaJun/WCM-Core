# Candidate validation

Validated on 2026-10-24 using macOS arm64, Python 3.12.14, Apple Clang,
SymPy 1.14.0 and native Z3 4.16.0.

## Executed

| Check | Result |
|---|---|
| C17 Cell regression | 49 cases passed |
| Optical framing | 4 cases passed |
| Energy arithmetic | 8 cases passed |
| Closed-loop and mid-frame power interruption | Passed |
| Two-lane SPSC host stress | Passed, 20,000 attempts per producer |
| C17 Mission-64 parser | Passed |
| HC Python tests | 16 passed |
| Generated combinational output cones | 53 forbidden-output queries passed |
| Selected top-level Python tests | 27 passed |
| Finite SMT specification queries | 31 UNSAT; 1 expected SAT mutation |
| Native virtual-device smoke run | 3 reports, 96 output symbols |
| Native C17 scenario smoke runs | All five scenarios passed |

The selected Python cases cover offline task compilation and provisioning,
Film behavioral models, Film source packaging and install refusal, malformed
archives, source pins and evidence hashes, and cross-language mission checks.
Differential cases use 6,000 raw images, 1,000 valid configurations with 8,000
scheduling comparisons, and 128 valid images with all 64 single-bit changes.

| Scenario | Completed reports | Output symbols | Boots |
|---|---:|---:|---:|
| nominal | 3 | 96 | 1 |
| brownout | 4 | 128 | 2 |
| sensor-silent | 0 | 0 | 1 |
| energy-starve | 0 | 0 | 1 |
| fault-inflight | 0 | 4 | 1 |

The native smoke checks compiled the candidate C17 sources directly on macOS.
Linux image builder and installer checks are listed separately below.
For the formal rerun, a validation-only library-location adapter loaded the
installed native Z3 library; the candidate generated and evaluated its own
unchanged SMT queries. The report contains the actual solver results.

## Not executed on this candidate

- The complete Linux `make test` and virtual image build/install/boot workflow.
- The eight Linux installer-based lifecycle tests and three other Python
  cases requiring the Linux image builder.
- Icarus Verilog simulation, complete endpoint HDL execution, Yosys synthesis,
  sequential RTL equivalence, or SVA properties.
- Physical storage, sensors, energy frontends, optical channel or actuator tests.
- Hosted GitHub Actions. The workflow is supplied for subsequent execution.

Formal coverage and target-frontend assumptions are described in
`docs/FORMAL_VERIFICATION.md`.
