// g_uart_top.sv -- UART pins <-> HLS evaluator of g.
//
//   uart_rxd -> uart_rx -> rx FIFO -> g_uart_kernel (Vitis HLS, DSPFP32) -> tx FIFO -> uart_tx -> uart_txd
//
// Protocol (see hls/g_eval.h):
//   request 0xA5, x[4], y[4], xor   -> reply 0x5A, re[4], im[4], e[4], flags, xor
//   g(x + iy) = (re + i im) * 2^e    (little-endian IEEE-754 fp32 / int32)
//
// g_uart_kernel is the RTL exported by Vitis HLS (hls/run_hls.tcl); its AXI-Stream
// ports for hls::stream<uint8_t> rx / tx are rx_TDATA/rx_TVALID/rx_TREADY and
// tx_TDATA/tx_TVALID/tx_TREADY, with ap_ctrl_none (free running).
module g_uart_top #(
    parameter integer CLK_HZ = 250_000_000,
    parameter integer BAUD   = 115_200
) (
    input  wire clk,
    input  wire rst_n,        // active-low, synchronous to clk
    input  wire uart_rxd,
    output wire uart_txd,
    output reg  rx_overrun,   // sticky: a byte arrived while the RX FIFO was full
    output wire rx_frame_err  // last received byte had a bad stop bit
);
    wire [7:0] rx_byte;
    wire       rx_valid;
    wire       rxq_ready;
    wire [7:0] k_rx_data;
    wire       k_rx_valid, k_rx_ready;
    wire [7:0] k_tx_data;
    wire       k_tx_valid, k_tx_ready;
    wire [7:0] txq_data;
    wire       txq_valid, txq_ready;

    uart_rx #(.CLK_HZ(CLK_HZ), .BAUD(BAUD)) u_rx (
        .clk(clk), .rst_n(rst_n), .rxd(uart_rxd),
        .m_tdata(rx_byte), .m_tvalid(rx_valid), .frame_err(rx_frame_err));

    always @(posedge clk) begin
        if (!rst_n) rx_overrun <= 1'b0;
        else if (rx_valid && !rxq_ready) rx_overrun <= 1'b1;
    end

    // buffers requests that arrive while the kernel is still computing
    axis_fifo #(.W(8), .DEPTH(64)) u_rxq (
        .clk(clk), .rst_n(rst_n),
        .s_tdata(rx_byte), .s_tvalid(rx_valid), .s_tready(rxq_ready),
        .m_tdata(k_rx_data), .m_tvalid(k_rx_valid), .m_tready(k_rx_ready));

    g_uart_kernel u_kernel (
        .ap_clk(clk), .ap_rst_n(rst_n),
        .rx_TDATA(k_rx_data), .rx_TVALID(k_rx_valid), .rx_TREADY(k_rx_ready),
        .tx_TDATA(k_tx_data), .tx_TVALID(k_tx_valid), .tx_TREADY(k_tx_ready));

    axis_fifo #(.W(8), .DEPTH(32)) u_txq (
        .clk(clk), .rst_n(rst_n),
        .s_tdata(k_tx_data), .s_tvalid(k_tx_valid), .s_tready(k_tx_ready),
        .m_tdata(txq_data), .m_tvalid(txq_valid), .m_tready(txq_ready));

    uart_tx #(.CLK_HZ(CLK_HZ), .BAUD(BAUD)) u_tx (
        .clk(clk), .rst_n(rst_n),
        .s_tdata(txq_data), .s_tvalid(txq_valid), .s_tready(txq_ready),
        .txd(uart_txd));
endmodule
