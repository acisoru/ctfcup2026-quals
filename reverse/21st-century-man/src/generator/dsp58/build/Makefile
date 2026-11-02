# Versal (DSP58 / DSPFP32) build of the g(x, y) UART evaluator.
#
#   make             full flow -> firmware.pdi     (Vitis HLS + Vivado on PATH)
#   make csim        C model vs double-precision reference (g++ only)
#   make sim         UART RTL simulation           (Icarus Verilog)
#   make emulator    desktop program speaking the UART protocol (host/g_client.py --emulator)
#   make coeffs      regenerate ROMs + test vectors from MODEL
#
# Stages (cf. yosys -> nextpnr -> icepack):
#   ../hls/*.cpp --vitis-run (HLS)--> g_hls/ (RTL IP) --vivado synth--> synth.dcp
#     --place & route--> routed.dcp --write_device_image--> firmware.pdi
.PHONY: all clean csim sim emulator coeffs

MODEL   ?= ../model/hello.json
PART    ?= xcvc1902-vsva2197-2MP-e-S
BOARD   ?=
XDC     ?= ../constraints/uart_pins.xdc
CLK_MHZ ?= 250
BAUD    ?= 115200
HLS     ?= vitis-run --mode hls --tcl
VIVADO  ?= vivado -mode batch -nojournal -notrace
export PART BOARD XDC CLK_MHZ BAUD

all: firmware.pdi

../hls/g_coeffs.h: $(MODEL) ../tools/gen_coeffs.py
	python3 ../tools/gen_coeffs.py $(MODEL) --out ../hls

hls.stamp: ../hls/g_eval.cpp ../hls/g_eval.h ../hls/g_coeffs.h hls.tcl
	$(HLS) hls.tcl
	touch hls.stamp

synth.dcp: hls.stamp ../rtl/*.sv $(XDC) synth.tcl cips_bd.tcl
	$(VIVADO) -source synth.tcl

routed.dcp: synth.dcp pnr.tcl
	$(VIVADO) -source pnr.tcl

firmware.pdi: routed.dcp image.tcl
	$(VIVADO) -source image.tcl

coeffs: ../hls/g_coeffs.h

csim: ../hls/g_coeffs.h
	g++ -O2 -std=c++14 -Wno-unknown-pragmas -Wno-unused-label -I../hls/sim_shim -I../hls ../hls/g_eval.cpp ../hls/tb_g_eval.cpp -o tb_g_eval
	./tb_g_eval

sim:
	iverilog -g2012 -o tb_uart.vvp ../rtl/uart_rx.sv ../rtl/uart_tx.sv ../rtl/axis_fifo.sv ../rtl/g_uart_top.sv ../rtl/sim/g_uart_kernel_stub.sv ../rtl/sim/tb_g_uart_top.sv
	vvp -n tb_uart.vvp

emulator: g_uart_emulator

g_uart_emulator: ../hls/g_eval.cpp ../hls/g_eval.h ../hls/g_coeffs.h ../hls/g_uart_emulator.cpp
	g++ -O2 -std=c++14 -Wno-unknown-pragmas -Wno-unused-label -I../hls/sim_shim -I../hls ../hls/g_eval.cpp ../hls/g_uart_emulator.cpp -o g_uart_emulator

clean:
	rm -rf hls.stamp g_hls vivado_proj .Xil reports synth.dcp routed.dcp firmware.pdi *.log *.jou tb_g_eval tb_uart.vvp g_uart_emulator
