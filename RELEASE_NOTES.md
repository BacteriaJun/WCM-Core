# WCM-Core v1.0.0

Reference control system for offline-configured autonomous endpoints.

The release includes a C17 controller, fixed-function Verilog, host task and
image tools, a Linux virtual device, regression tests and finite specification
models. Supported tasks are threshold-triggered and periodic reports with a
configured report count. Action authorization uses current evidence, available
energy and transaction-completion feedback.

`virtual-node` runs on a matching Linux host. `film-reference` supplies RTL
source for target-specific integration. Hardware integration and validation
status are recorded in `docs/VALIDATION_1_0_0.md`.

Public identifiers and technical documentation have been normalized for this
release. The Mission-64 binary format is unchanged.
