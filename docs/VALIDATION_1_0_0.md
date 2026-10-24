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

## Hosted Linux validation

[GitHub Actions run 40050520847](https://github.com/BacteriaJun/WCM-Core/actions/runs/40050520847)
passed on implementation commit `90b967c5bf76b3686ff6c0226fb27e057e023ae1`.

| Check | Result |
|---|---|
| Full Linux `make test` | Passed, including 38 top-level and 16 HC Python tests |
| Finite SMT suite | 31 UNSAT; 1 expected SAT mutation |
| Film RTL | Serial-loader simulation and complete endpoint elaboration passed |
| HC RTL | Directed bench, 780-cycle reference trace and asynchronous frontend bench passed |
| Generic Yosys synthesis | Complete endpoint synthesis passed |
| Release evidence audit | Passed |
| Virtual image workflow | Build, install and boot passed |
| Physical-target install guard | Film source target correctly refused installation |

HDL validation included two identifier portability corrections and an
acceptance-edge timing correction in the directed HC testbench. All 17
failure assertions in that bench were retained.

## Hardware integration

Target-specific frontend, storage, optical and actuator qualification is
pending. Sequential RTL equivalence and physical hardware testing remain
separate integration tasks. Formal coverage and frontend assumptions are
specified in `docs/FORMAL_VERIFICATION.md`.
