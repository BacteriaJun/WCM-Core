# Mission-64 v1

Mission-64 is an 8-byte configuration for threshold-triggered or periodic
reports. Host tools compile a `[mission]` TOML source, create per-node binary
files and verify their contents by readback.

At startup, the endpoint loads stored configuration and checks its version,
fields and CRC. Local sensor evidence, task policy and energy checks govern
execution. Configuration is fixed during operation; communication uses a
two-state reflected-light uplink.

## Mission-64 bit encoding (network-order, MSB first)

| Field | Bits | Semantics |
|---|---:|---|
| `version` | 4 | exactly 1 |
| `task` | 4 | 1 threshold-triggered report; 2 periodic report |
| `sensor` | 4 | 1 local scalar input; other types unsupported |
| `threshold` | 6 | threshold-report: 1..63, compare `sensor >= 10*threshold`; periodic: 0 |
| `sample_period` | 6 | 1..63, tick interval `index * 1000 us` **in the virtual profile** |
| `report_period` | 6 | 1..63, minimum gap `index * 10000 us` **in the virtual profile** |
| `max_reports` | 6 | 1..63 reports, then passive mission termination |
| `seed` | 12 | per-node configuration token; `(seed%16)*1000 us` selects one of 16 initial report-delay slots |
| `flags` | 8 | zero; other bit patterns reserved and rejected |
| `CRC-8/ATM` | 8 | CRC polynomial `0x07`, init `0`, no reflection/final xor, over first 7 bytes |

The task vocabulary and bit fields define the supported behavior.
The canonical example in `devices/virtual-node/mission.toml` is
`11 11 81 04 30 00 00 f7`. CRC and distribution integrity are described in
`SECURITY.md`.

## Local execution

The virtual reference samples the scalar sensor and derives task authority
through Cell's `WCM_R4_LOCAL_POLICY` lane. Cell applies evidence-validity,
energy and transaction checks before emitting a 32-bit report frame.
Sensor values, charging and physical callbacks use host simulation models.

The Film implementation includes a serial Mission-64 loader and local policy
state machine. Storage, timebase, sensor and output frontends bind to the
selected hardware target. Integration status is in `docs/VALIDATION_1_0_0.md`.

## Offline workflow

```sh
python3 tools/wcmctl.py mission-compile \
  --source devices/virtual-node/mission.toml --out /tmp/wcm-mission.bin
python3 tools/wcmctl.py provision-batch \
  --mission /tmp/wcm-mission.bin --count 16 --out /tmp/wcm-batch
python3 tools/wcmctl.py build --device virtual-node \
  --mission /tmp/wcm-batch/node-00007.bin --out /tmp/wcm-device-7
python3 tools/wcmctl.py install --bundle /tmp/wcm-device-7 \
  --device-root /tmp/wcm-installed-7
python3 tools/wcmctl.py boot --device-root /tmp/wcm-installed-7
```

Batch provisioning produces binary files and a readback/hash manifest.
