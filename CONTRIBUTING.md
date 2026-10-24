# Contributing

Changes should preserve the offline task format and evidence, energy and
transaction authorization rules.

1. Run `make test` on Linux and record the tool versions and results.
2. For task encoding or RTL changes, update behavioral tests and examine drift
   between the implementation and formal specification models.
3. Review source changes before updating formal source hash pins. Hashes record source
   identity; evaluate implementation correspondence through model and RTL checks.
4. With Icarus Verilog and Yosys available, run `make film-rtl-test`,
   `make hc-rtl-test` and `make film-synth`.
5. Include reproductions for fault, timing, stale evidence, incomplete storage
   and transaction settlement failures.
6. Keep validation limits and device capability flags accurate.

Retain applicable license and attribution notices. Do not commit credentials.
Report security issues as described in SECURITY.md.
