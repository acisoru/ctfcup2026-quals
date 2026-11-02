// g_top.v -- chip top: UART pins <-> g_kernel, with a power-on reset.
//
//   uart_rxd -> uart_rx -> rx FIFO -> g_kernel -> tx FIFO -> uart_tx -> uart_txd
//
// CLK_HZ and BAUD only set the UART bit period (CLK_HZ / BAUD clocks per bit);
// the evaluator itself is clock-agnostic.
`default_nettype none

module g_top #(
    parameter integer CLK_HZ = 200_000_000,
    parameter integer BAUD   = 921_600
) (
    input  wire clk,
    input  wire uart_rxd,
    output wire uart_txd
);
    // iCE40 flip-flops come up as 0 after configuration: hold reset for 15 clocks
    reg [3:0] por = 4'd0;
    wire      rst_n = por[3];
    always @(posedge clk) if (!por[3]) por <= por + 4'd1;

    wire [7:0] rx_byte;
    wire       rx_valid, rx_frame_err;
    wire [7:0] k_rx_data, k_tx_data, txq_data;
    wire       k_rx_valid, k_rx_ready, k_tx_valid, k_tx_ready, txq_valid, txq_ready;
    wire       rxq_ready;

    uart_rx #(.CLK_HZ(CLK_HZ), .BAUD(BAUD)) u_rx (
        .clk(clk), .rst_n(rst_n), .rxd(uart_rxd),
        .m_tdata(rx_byte), .m_tvalid(rx_valid), .frame_err(rx_frame_err));

    // buffers requests that arrive while the kernel is still computing
    axis_fifo #(.W(8), .DEPTH(64)) u_rxq (
        .clk(clk), .rst_n(rst_n),
        .s_tdata(rx_byte), .s_tvalid(rx_valid), .s_tready(rxq_ready),
        .m_tdata(k_rx_data), .m_tvalid(k_rx_valid), .m_tready(k_rx_ready));

    g_kernel u_kernel (
        .clk(clk), .rst_n(rst_n),
        .rx_data(k_rx_data), .rx_valid(k_rx_valid), .rx_ready(k_rx_ready),
        .tx_data(k_tx_data), .tx_valid(k_tx_valid), .tx_ready(k_tx_ready));

    axis_fifo #(.W(8), .DEPTH(32)) u_txq (
        .clk(clk), .rst_n(rst_n),
        .s_tdata(k_tx_data), .s_tvalid(k_tx_valid), .s_tready(k_tx_ready),
        .m_tdata(txq_data), .m_tvalid(txq_valid), .m_tready(txq_ready));

    uart_tx #(.CLK_HZ(CLK_HZ), .BAUD(BAUD)) u_tx (
        .clk(clk), .rst_n(rst_n),
        .s_tdata(txq_data), .s_tvalid(txq_valid), .s_tready(txq_ready),
        .txd(uart_txd));
endmodule
