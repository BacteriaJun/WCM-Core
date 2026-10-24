# Architecture

WCM-Core controls fixed sensing and reporting tasks on an autonomous endpoint.

```text
Task TOML -> host compiler -> Mission-64 image -> offline provisioning
                                                     |
                            local task policy <- stored configuration
                                    |
                 sensor evidence + energy qualification
                                    |
                         guarded action authorization
                                    |
                   reflected-light output / actuation
                                    |
                     qualified transaction completion
```

## Components

| Component | Function | Implementation |
|---|---|---|
| Cell | Evidence freshness, continuity, energy and transaction control | C17 |
| Film | Fixed-function control and serial task loading | Verilog |
| HC | Configuration validation and specialized RTL generation | Host Python |
| Energy | Conservative capacitor-energy arithmetic | Reference C17 model |
| Optical | Two-state reflected-symbol frame encoding | C17 encoder |
| Tools | Build, verify, install, boot and environmental scenarios | Host Python/C17 |

Cell uses sensor evidence and locally derived policy authority. A continuity
break revokes previous evidence. Outstanding or interrupted physical work
cannot create fresh energy credit without qualified settlement and a later
measurement. A completion token must correspond to the dispatched transaction.

Mission-64 stores a versioned fixed task configuration. The loader rejects
invalid lengths, fields or CRC. Task behavior follows the fixed configuration fields.

`virtual-node` is a native Linux executable with mock inputs and outputs.
`film-reference` packages RTL source and task data for hardware integration.
The Cell reference emits a 32-bit frame; the Film demonstration uses an 8-bit
test frame. Cross-model checks compare task and transaction behavior.

The endpoint has no station-command or acknowledgment input. Sensor, energy,
clock, storage and settlement inputs remain explicit hardware contracts.
