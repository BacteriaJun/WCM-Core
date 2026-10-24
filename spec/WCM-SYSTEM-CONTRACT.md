# Control contract

This contract describes the reference endpoint control behavior shared by
Cell, Film and the host toolchain.

1. Physical action authority requires evidence acquired after the most recent
   continuity cutover and valid for the relevant action horizon.
2. Dependent evidence changes revoke prior authority.
3. Energy qualification must conservatively cover the complete transaction,
   including startup, physical effect and reserve. Measurements predating
   unsettled expenditure cannot create new credit for that expenditure.
4. Outstanding or interrupted physical work blocks new active transactions
   until qualified settlement. Software acknowledgment alone is insufficient.
5. Brownout, trusted-time loss, observation continuity loss or recognized
   hardware fault revokes authorization. Independent hardware gating must
   protect outputs where software or clock timing is insufficient.
6. Sensor, energy, clock, storage and settlement inputs require qualified
   frontends. Local task authority derives from validated stored configuration
   and current local evidence.
7. Endpoint output consists of two reflected states. No downlink command or
   acknowledgment receiver is defined.

## Task profile

Mission-64 v1 is an 8-byte fixed-function configuration. Its task fields cannot
override evidence, energy, continuity or physical settlement gates. See
`docs/MISSION_64_V1.md`.

## Conformance boundary

The Linux virtual target runs with mock drivers. The Film target provides RTL
for hardware integration. HDL execution and target hardware checks are tracked
in `docs/VALIDATION_1_0_0.md`; specification coverage and frontend assumptions
are described in `docs/FORMAL_VERIFICATION.md`.
