// system_top.sv -- Versal top level: CIPS block design (PL clock + reset) and
// the UART evaluator of g.  Not used in simulation (needs the block design).
module system_top #(
    parameter integer CLK_HZ = 250_000_000,
    parameter integer BAUD   = 115_200
) (
    input  wire uart_rxd,
    output wire uart_txd
);
    wire clk;
    wire bd_resetn;

    cips_bd_wrapper u_bd (
        .pl_clk(clk),
        .pl_resetn(bd_resetn));

    // synchronise the reset release to clk
    (* ASYNC_REG = "TRUE" *) reg [2:0] rst_sync;
    always @(posedge clk or negedge bd_resetn) begin
        if (!bd_resetn) rst_sync <= 3'b000;
        else            rst_sync <= {rst_sync[1:0], 1'b1};
    end

    g_uart_top #(.CLK_HZ(CLK_HZ), .BAUD(BAUD)) u_g (
        .clk(clk),
        .rst_n(rst_sync[2]),
        .uart_rxd(uart_rxd),
        .uart_txd(uart_txd),
        .rx_overrun(),
        .rx_frame_err());
endmodule
