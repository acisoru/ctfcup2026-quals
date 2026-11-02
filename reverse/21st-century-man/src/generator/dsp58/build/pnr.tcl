# pnr.tcl -- place & route: synth.dcp -> routed.dcp
open_checkpoint synth.dcp

# the UART pins must be set in the XDC (see constraints/uart_pins.xdc)
foreach p {uart_rxd uart_txd} {
    if {[get_property PACKAGE_PIN [get_ports $p]] eq ""} {
        error "port $p has no PACKAGE_PIN: set the UART pins for your board in constraints/uart_pins.xdc"
    }
}

opt_design
place_design
phys_opt_design
route_design
write_checkpoint -force routed.dcp
file mkdir reports
report_timing_summary -file reports/timing_routed.rpt
report_utilization -file reports/utilization_routed.rpt
if {[get_property SLACK [get_timing_paths -max_paths 1 -nworst 1 -setup]] < 0} {
    puts "WARNING: timing not met; lower CLK_MHZ (e.g. make CLK_MHZ=200)"
}
