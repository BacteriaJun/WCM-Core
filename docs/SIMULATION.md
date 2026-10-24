# Reproducible time-stepped node lifecycle

The host harness runs the WCM-Cell R4 C17 controller with a stored Mission-64
image. Scenarios drive synthetic sensor and power callbacks.

```bash
python3 tools/wcmctl.py build --device virtual-node --out /tmp/wcm-vsim
python3 tools/wcmctl.py install --bundle /tmp/wcm-vsim --device-root /tmp/wcm-installed
python3 tools/wcmctl.py simulate --device-root /tmp/wcm-installed --scenario nominal --ticks 250
python3 tools/wcmctl.py simulate --device-root /tmp/wcm-installed --scenario brownout --ticks 250
python3 tools/wcmctl.py simulate --device-root /tmp/wcm-installed --scenario fault-inflight --ticks 250
```

Scenarios: `nominal` (finite mission goes passive); `brownout` (cold restart
replays the mission from immutable NVM, so an earlier report can repeat);
`sensor-silent` (no reports); `energy-starve` (no reports); `fault-inflight`
(interrupt after four symbols, prevent report count increment, World Break and
safe output). `--ticks` sets the host simulation duration.

`simulate` returns JSON event records and a summary of emitted mock symbols,
completed reports, restarts and interruptions. The scenarios exercise bounded
control behavior with synthetic inputs; target timing, energy and optical
measurements belong to hardware validation.
