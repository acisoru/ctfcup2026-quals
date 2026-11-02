# synth.tcl -- Vivado synthesis -> synth.dcp
#   HLS IP (g_hls/sol1/impl/ip) + ../rtl/*.sv + CIPS block design, top = system_top
proc getenv {name default} {
    if {[info exists ::env($name)] && $::env($name) ne ""} { return $::env($name) }
    return $default
}
set part    [getenv PART xcvc1902-vsva2197-2MP-e-S]
set board   [getenv BOARD ""]
set xdc     [getenv XDC ../constraints/uart_pins.xdc]
set clk_mhz [getenv CLK_MHZ 250]
set baud    [getenv BAUD 115200]
file mkdir reports

create_project -force g_proj ./vivado_proj -part $part
if {$board ne ""} { set_property board_part $board [current_project] }
set_property target_language Verilog [current_project]

# the evaluator exported by hls.tcl
set_property ip_repo_paths [list [file normalize ./g_hls/sol1/impl/ip]] [current_project]
update_ip_catalog
create_ip -vlnv xilinx.com:hls:g_uart_kernel:1.0 -module_name g_uart_kernel
generate_target all [get_ips g_uart_kernel]

# UART + glue RTL and pin constraints
add_files [glob ../rtl/*.sv]
add_files -fileset constrs_1 $xdc

# CIPS: PL clock and reset
source cips_bd.tcl
generate_target all [get_files cips_bd.bd]
add_files -norecurse [make_wrapper -files [get_files cips_bd.bd] -top]

set_property top system_top [current_fileset]
set_property generic "CLK_HZ=[expr {int($clk_mhz * 1000000)}] BAUD=$baud" [current_fileset]

launch_runs synth_1 -jobs 4
wait_on_run synth_1
if {[get_property PROGRESS [get_runs synth_1]] ne "100%"} { error "synthesis failed" }
open_run synth_1
write_checkpoint -force synth.dcp
report_utilization -file reports/utilization_synth.rpt
report_utilization -cells [get_cells -hier -filter {REF_NAME =~ DSP*}] -file reports/dsp_synth.rpt
