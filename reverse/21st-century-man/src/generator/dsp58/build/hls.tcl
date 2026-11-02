# hls.tcl -- Vitis HLS: hls/g_eval.cpp -> RTL IP in g_hls/sol1/impl/ip
#   run from build/:  vitis-run --mode hls --tcl hls.tcl      (Vitis 2023.2+)
#                     vitis_hls -f hls.tcl                     (older releases)
proc getenv {name default} {
    if {[info exists ::env($name)] && $::env($name) ne ""} { return $::env($name) }
    return $default
}
set part    [getenv PART xcvc1902-vsva2197-2MP-e-S]
set clk_mhz [getenv CLK_MHZ 250]

open_project -reset g_hls
set_top g_uart_kernel
add_files ../hls/g_eval.cpp -cflags "-I../hls"
add_files -tb ../hls/tb_g_eval.cpp -cflags "-I../hls"

open_solution -reset sol1 -flow_target vivado
set_part $part
create_clock -period [expr {1000.0 / $clk_mhz}] -name default

# every fp32 multiply / add / subtract on a DSP58 slice in DSPFP32 mode
config_op fmul -impl primitivedsp
config_op fadd -impl primitivedsp
config_op fsub -impl primitivedsp

csim_design
csynth_design
export_design -format ip_catalog -rtl verilog
exit
