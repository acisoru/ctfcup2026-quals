# iCE40 build of the g(x, y) UART evaluator, and its way back to a C++ device.
#
#   make                 model -> ROM -> yosys -> nextpnr-ice40 -> icepack -> build/g.bin
#   make cxx             build/g.bin -> iceunpack -> icebox_vlog -> yosys -> build/cxx/design.cc
#   make device          compile build/cxx with the UART harness and run it on a pty
#   make sim             RTL regression (iverilog, UART level, every 7th test vector)
#   make check           query the running device (make device) at 200 random points
#                        and compare with double precision (dsp58/host/g_client.py)
#   make image           build the Docker builder image (done automatically when needed)
#   make clean
#
# Parameters (override on the command line):
#   CLK_MHZ=200 BAUD=921600      UART bit period = CLK_MHZ*1e6 / BAUD clocks
#   DEVICE=up5k PACKAGE=sg48     nextpnr-ice40 device / package; PCF=pcf/$(DEVICE)_$(PACKAGE).pcf
#   MODEL_RAW=model/flag_raw.json   text_lemniscate output; MODEL=model/flag.json is made
#                                from it by tools/scale_model.py (scaled, quantised)
#   NATIVE=1                     run the tools from $PATH instead of the Docker image
#
# The text function g is only ~7 MHz on a UP5K, so place & route is run with
# --timing-allow-fail: the bitstream is meant to be simulated (make device), the
# clock/baud ratio only sets the UART timing.

CLK_MHZ ?= 200
BAUD    ?= 921600
DEVICE  ?= up5k
PACKAGE ?= sg48
MODEL_RAW ?= model/flag_raw.json
MODEL   ?= model/flag.json
PCF     ?= pcf/$(DEVICE)_$(PACKAGE).pcf
IMAGE   ?= g-ice40
CLK_HZ  := $(shell echo $$(( $(CLK_MHZ) * 1000000 )))

RTL := rtl/axis_fifo.v rtl/uart_rx.v rtl/uart_tx.v rtl/g_kernel.v rtl/g_top.v
GEN := gen/rom.hex gen/orders.vh gen/params.vh gen/vectors.txt

# ---- how to run a tool: inside the builder image, or natively ---------------
ifeq ($(NATIVE),1)
RUN :=
image:
	@true
else
# the parent directory is mounted so that ../dsp58/model is visible
RUN := docker run --rm -i -u $$(id -u):$$(id -g) -v "$(abspath ..):/work" -w /work/ice40 $(IMAGE)
image: build/.image
build/.image: Dockerfile
	docker build -t $(IMAGE) .
	@mkdir -p build && touch $@
endif

.PHONY: all bitstream cxx device sim check image clean rom
all: bitstream
bitstream: build/g.bin
rom: $(GEN)
cxx: build/cxx/design.cc

# ---- 0. text_lemniscate model -> scaled into [-4, 4), coefficients quantised to Q4.12
$(MODEL): $(MODEL_RAW) tools/scale_model.py | image
	$(RUN) python3 tools/scale_model.py $(MODEL_RAW) $(MODEL)

# ---- 1. model -> fixed-point tables ------------------------------------------
$(GEN): tools/gen_rom.py $(MODEL) | image
	$(RUN) python3 tools/gen_rom.py $(MODEL) --out gen

# ---- 2. synthesis -----------------------------------------------------------
build/g.json: $(RTL) $(GEN) | image
	@mkdir -p build
	$(RUN) yosys -q -l build/synth.log -p "\
	    read_verilog -I gen $(RTL); \
	    chparam -set CLK_HZ $(CLK_HZ) -set BAUD $(BAUD) g_top; \
	    synth_ice40 -top g_top -json build/g.json"
	@grep -E 'SB_LUT4|SB_RAM40_4K|SB_DFF' build/synth.log | sort | uniq | sed 's/^/    /'

# ---- 3. place & route ----------------------------------------------------------
build/g.asc: build/g.json $(PCF) | image
	$(RUN) nextpnr-ice40 --$(DEVICE) --package $(PACKAGE) --json build/g.json --pcf $(PCF) \
	    --asc build/g.asc --freq $(CLK_MHZ) --timing-allow-fail -q -l build/pnr.log
	@grep -E 'Device utilisation|ICESTORM_LC|ICESTORM_RAM|Max frequency' build/pnr.log | sed 's/^Info: //'

# ---- 4. bitstream ("binary stream") --------------------------------------------
build/g.bin: build/g.asc | image
	$(RUN) icepack build/g.asc build/g.bin
	@ls -l build/g.bin

# ---- 5. bitstream -> C++ -------------------------------------------------------------
build/cxx/design.cc: build/g.bin tools/bitstream2cxx.sh | image
	$(RUN) tools/bitstream2cxx.sh -p $(PCF) build/g.bin build/cxx

# ---- 6. C++ -> running serial device ---------------------------------------------------
# The device is compiled and run on the host (the pty has to live here), so this
# needs a host g++. build/cxx is self-contained: design.cc plus the cxxrtl headers.
# A symlink to the pty appears at build/g_uart; the pty path is also printed.
device: build/cxx/design.cc
	tools/run_device.sh -c $(CLK_HZ) -b $(BAUD) -l build/g_uart build/cxx

# ---- simulations ---------------------------------------------------------------------------
# a 16 clocks/bit UART keeps the RTL run short; the arithmetic does not depend on it
sim: $(RTL) $(GEN) sim/tb_top.v | image
	@mkdir -p build
	$(RUN) iverilog -g2012 -I gen -DCLK_HZ=16000000 -DBAUD=1000000 -o build/tb sim/tb_top.v $(RTL)
	$(RUN) vvp -n build/tb +N=450 +STRIDE=7

# needs a running `make device` (pty symlink build/g_uart) and pyserial on the host
check:
	python3 ../dsp58/host/g_client.py --port build/g_uart --baud $(BAUD) --timeout 30 --check $(MODEL) --n 200

clean:
	rm -rf build gen
