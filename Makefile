PYTHON ?= python3
CC ?= gcc
CFLAGS := -std=c17 -Os -Wall -Wextra -Wpedantic -Wconversion -Wshadow -Werror
INC := -Isystem/cell -Isystem/optical -Isystem/energy -Isystem/mission -Itests/integration
SRC := system/cell/wcm_cell_r4.c system/optical/wcm_optical.c system/energy/wcm_power_model.c system/mission/wcm_mission64.c
BUILD := build
.PHONY: help cell-check hc-check film-check formal-check test preview release-clean film-synth hc-rtl-test lifecycle-check release-audit
help:
	@echo 'make test | python3 tools/wcmctl.py build --device virtual-node --out dist/virtual-node'
$(BUILD):
	mkdir -p $@
cell-check: | $(BUILD)
	$(CC) $(CFLAGS) $(INC) tests/integration/test_r4.c system/cell/wcm_cell_r4.c system/optical/wcm_optical.c -o $(BUILD)/test_r4
	$(BUILD)/test_r4
	$(CC) $(CFLAGS) $(INC) tests/integration/test_optical.c tests/integration/wcm_optical_test_receiver.c system/optical/wcm_optical.c -o $(BUILD)/test_optical
	$(BUILD)/test_optical
	$(CC) $(CFLAGS) $(INC) tests/integration/test_power.c system/energy/wcm_power_model.c -o $(BUILD)/test_power
	$(BUILD)/test_power
	$(CC) $(CFLAGS) $(INC) tests/integration/test_closed_loop.c tests/integration/wcm_optical_test_receiver.c $(SRC) -o $(BUILD)/test_closed_loop
	$(BUILD)/test_closed_loop
	$(CC) $(CFLAGS) $(INC) tests/integration/stress_spsc.c system/cell/wcm_cell_r4.c -pthread -o $(BUILD)/stress_spsc
	$(BUILD)/stress_spsc
hc-check:
	$(MAKE) -C toolchain/hc check cone-check
formal-check:
	$(PYTHON) verification/formal/source_guard.py
	$(PYTHON) verification/formal/prove.py
film-rtl-test:
	@command -v iverilog >/dev/null || (echo "ERROR: Icarus Verilog not installed; cannot execute RTL tests" >&2; exit 2)
	@command -v vvp >/dev/null || (echo "ERROR: vvp missing" >&2; exit 2)
	mkdir -p build
	iverilog -g2012 -Wall -s tb_wcm_mission64_engine -o build/tb_mission64 hardware/film/rtl/wcm_mission64_engine.v hardware/film/tb/tb_wcm_mission64_engine.v
	vvp build/tb_mission64
	rm -rf build/film-rtl-preview
	$(PYTHON) tools/wcmctl.py build --device film-reference --out build/film-rtl-preview
	iverilog -g2012 -Wall -s wcm_mission64_endpoint -o build/film_endpoint build/film-rtl-preview/rtl/wcm_reference_core.v build/film-rtl-preview/rtl/wcm_mission64_engine.v build/film-rtl-preview/rtl/wcm_mission64_endpoint.v
hc-rtl-test:
	$(MAKE) -C toolchain/hc rtl-test
film-synth:
	@command -v yosys >/dev/null || (echo "ERROR: Yosys unavailable; no synth result" >&2; exit 2)
	mkdir -p build/film-synth
	$(PYTHON) tools/wcmctl.py build --device film-reference --out build/film-synth/image
	yosys -Q -T -p "read_verilog build/film-synth/image/rtl/wcm_reference_core.v build/film-synth/image/rtl/wcm_mission64_engine.v build/film-synth/image/rtl/wcm_mission64_endpoint.v; hierarchy -check -top wcm_mission64_endpoint; synth -top wcm_mission64_endpoint; stat" > build/film-synth/report.txt
lifecycle-check:
	$(PYTHON) -m unittest discover -s tests -p test_lifecycle.py -v
	$(PYTHON) -m unittest discover -s tests -p test_c_mission_differential.py -v
release-audit:
	$(PYTHON) tools/release_audit.py --check
film-check:
	$(PYTHON) -m unittest discover -s tests -p test_film*.py -v
	test -f hardware/film/rtl/wcm_film_p1.v
preview:
	$(PYTHON) tools/wcmctl.py build --device virtual-node --out dist/virtual-node
	$(PYTHON) tools/wcmctl.py install --bundle dist/virtual-node --device-root dist/virtual-installed
	$(PYTHON) tools/wcmctl.py boot --device-root dist/virtual-installed
	$(PYTHON) tools/wcmctl.py build --device film-reference --out dist/film-reference
	test -f dist/film-reference/rtl/wcm_reference_core.v
release-clean:
	rm -rf build dist toolchain/hc/build
mission-check: | $(BUILD)
	$(CC) $(CFLAGS) $(INC) tests/integration/test_mission.c system/mission/wcm_mission64.c -o $(BUILD)/test_mission
	$(BUILD)/test_mission
	$(PYTHON) -m unittest discover -s tests -p test_mission*.py -v

test: cell-check hc-check formal-check
	$(PYTHON) -m unittest discover -s tests -p 'test_*.py' -v
	test -f hardware/film/rtl/wcm_mission64_engine.v
	$(PYTHON) tools/release_audit.py --check
