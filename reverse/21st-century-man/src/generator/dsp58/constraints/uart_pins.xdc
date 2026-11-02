# uart_pins.xdc -- UART pins of system_top.  EDIT FOR YOUR BOARD.
#
# The clock comes from the CIPS (PL clock 0), so only the two UART pins are
# needed: route them to any PL I/O that reaches a USB-UART adapter (e.g. a PMOD
# or FMC header), 8N1 at BAUD (default 115200).  On Versal HD/XP banks use the
# bank's I/O voltage (LVCMOS12/15/18); 3.3 V needs an HD bank or level shifter.
# The build stops in pnr.tcl until both PACKAGE_PINs are set.
#
# set_property PACKAGE_PIN <pin> [get_ports uart_rxd]
# set_property PACKAGE_PIN <pin> [get_ports uart_txd]
# set_property IOSTANDARD LVCMOS18 [get_ports {uart_rxd uart_txd}]
set_property PULLUP true [get_ports uart_rxd]
