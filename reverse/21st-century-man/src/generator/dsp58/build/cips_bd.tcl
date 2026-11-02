# cips_bd.tcl -- minimal Versal block design: the CIPS (needed in every Versal
# design to build a PDI) providing one PL clock and a PL reset; nothing else of
# the processing system is used.  Sourced by synth.tcl.
#
# The PS_PMC_CONFIG keys below are those of recent Vivado releases; if your
# version rejects one, open the CIPS in IP integrator, set "PL clock 0 =
# CLK_MHZ" and "1 PL reset", and copy the resulting CONFIG.PS_PMC_CONFIG here.
create_bd_design cips_bd
set cips [create_bd_cell -type ip -vlnv xilinx.com:ip:versal_cips:* versal_cips_0]
set_property -dict [list \
    CONFIG.PS_PMC_CONFIG [list \
        PS_USE_PMCPL_CLK0            1 \
        PMC_CRP_PL0_REF_CTRL_FREQMHZ $clk_mhz \
        PS_NUM_FABRIC_RESETS         1 \
    ] \
] $cips

create_bd_port -dir O -type clk pl_clk
set_property CONFIG.FREQ_HZ [expr {int($clk_mhz * 1000000)}] [get_bd_ports pl_clk]
connect_bd_net [get_bd_pins versal_cips_0/pl0_ref_clk] [get_bd_ports pl_clk]
create_bd_port -dir O -type rst pl_resetn
connect_bd_net [get_bd_pins versal_cips_0/pl0_resetn] [get_bd_ports pl_resetn]

validate_bd_design
save_bd_design
