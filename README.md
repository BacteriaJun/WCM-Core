# WCM-Core

WCM-Core is a reference control system for resource-constrained autonomous
endpoints. It executes preconfigured sensing and reporting tasks, authorizes
physical actions using current evidence and energy checks, and revokes
authorization after faults or a loss of observation continuity.

## Components

- **Cell:** C17 evidence, energy and transaction control.
- **Film:** fixed-function Verilog control and serial task loader.
- **HC:** host tools for validated task configuration and specialized RTL generation.
- **Mission-64:** an 8-byte offline configuration for threshold or periodic reports.
- **Tools:** virtual image build, integrity verification, installation and simulation.

The endpoint emits two-state reflected-light symbols. Tasks are configured
before execution; no downlink command or acknowledgment interface is provided.

## Quick start

The virtual image requires Linux, Python 3.12+, and a C17 compiler.
Install Z3 separately as a command-line tool or shared library.

```sh
python3 -m pip install -r requirements-dev.txt
make test
python3 tools/wcmctl.py build --device virtual-node --out /tmp/wcm-image
python3 tools/wcmctl.py install --bundle /tmp/wcm-image --device-root /tmp/wcm-installed
python3 tools/wcmctl.py boot --device-root /tmp/wcm-installed
python3 tools/wcmctl.py simulate --device-root /tmp/wcm-installed --scenario brownout --ticks 250
```

`virtual-node` runs on the matching Linux host. `film-reference` produces
RTL source for target-specific hardware integration.

## Verification and documentation

`make formal-check` evaluates 32 SMT specification queries. `make hc-rtl-test`
and `make film-rtl-test` require Icarus Verilog; `make film-synth` requires Yosys.
Test results and hardware integration status are recorded in the
[validation record](docs/VALIDATION_1_0_0.md).

See the [documentation index](docs/INDEX.md), [validation record](docs/VALIDATION_1_0_0.md),
and [integrity and provisioning](SECURITY.md). Licensed under [Apache-2.0](LICENSE).
