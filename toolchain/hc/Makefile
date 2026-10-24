PYTHON ?= python3
SPEC = examples/reference_core.toml
TOP = wcm_reference_core
RTL = build/$(TOP).v
TB = build/tb_$(TOP).v

.PHONY: all compile check explore cone-check rtl-test synth clean
all: check cone-check
compile:
	$(PYTHON) src/compiler.py $(SPEC) --out build >/dev/null
check: compile
	$(PYTHON) -m unittest discover -s tests -v
cone-check: compile
	$(PYTHON) tools/check_rtl_cones.py $(RTL)
explore:
	$(PYTHON) -m unittest tests.test_reference.ReferenceTests.test_exploration -v
rtl-test: compile
	$(PYTHON) tools/gen_trace_tb.py
	@command -v iverilog >/dev/null || (echo "NOT EXECUTED: install iverilog and vvp"; exit 3)
	@command -v vvp >/dev/null || (echo "NOT EXECUTED: install vvp"; exit 3)
	iverilog -g2012 -s tb_$(TOP) -o build/sim.out $(RTL) $(TB)
	vvp build/sim.out
	iverilog -g2012 -s tb_trace_$(TOP) -o build/trace_sim.out $(RTL) build/tb_trace_$(TOP).v
	vvp build/trace_sim.out
	iverilog -g2012 -s tb_dirty_frontend -o build/dirty_sim.out rtl/sticky_change_frontend.v tb/tb_dirty_frontend.v
	vvp build/dirty_sim.out
synth: compile
	@command -v yosys >/dev/null || (echo "NOT EXECUTED: install yosys"; exit 3)
	yosys -Q -T -p "read_verilog $(RTL); hierarchy -top $(TOP); synth -top $(TOP); stat" | tee build/synth.txt
clean:
	rm -rf build
