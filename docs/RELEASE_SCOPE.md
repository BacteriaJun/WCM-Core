# Release scope

WCM-Core provides offline-configured endpoint sensing, reporting and guarded
physical transactions.

| Component | Supplied implementation |
|---|---|
| Cell | C17 evidence, continuity, energy and transaction control |
| Mission-64 | Threshold-report and periodic-report configuration |
| Film | Serial loader, policy engine, endpoint RTL and test benches |
| HC | Validated fixed-profile RTL generation |
| Optical | Binary reflected-state frame encoder |
| Host tools | File provisioning, virtual image installation and lifecycle scenarios |
| Verification | C17/Python tests and finite SMT specification queries |

The installable target is a matching Linux-host virtual image. The Film target
supplies RTL source; physical target integration and qualification are pending.
See the [validation record](VALIDATION_1_0_0.md) for executed and pending checks,
[formal models](FORMAL_VERIFICATION.md) for specification coverage, and
[integrity and provisioning](../SECURITY.md) for authentication assumptions.

Tasks are configured offline. Endpoint communication consists of reflected-state
uplink; downlink commands, acknowledgment and receiver-side signal processing
are outside the supplied interface.

Report progress is volatile. Cold restart can replay reports from the stored
configuration. Exactly-once physical actions require persistent completion
tracking beyond this reporting profile.
