all: traverse.bin

dfa.v: gen.py
	python3 gen.py dfa.v

traverse.json: top.v dfa.v
	yosys -q -p "synth_ice40 -top top -nobram -json $@" top.v

traverse.asc: traverse.json icestick.pcf
	nextpnr-ice40 -q --hx1k --package tq144 --seed 1 --json $< --pcf icestick.pcf --asc $@

traverse.bin: traverse.asc
	icepack $< $@

clean:
	rm -f dfa.v traverse.json traverse.asc traverse.bin

.PHONY: all clean
