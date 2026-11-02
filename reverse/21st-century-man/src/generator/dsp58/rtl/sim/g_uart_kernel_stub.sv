// g_uart_kernel_stub.sv -- SIMULATION ONLY stand-in for the Vitis HLS kernel,
// with the same ports and byte protocol: it parses a request (resyncing on
// 0xA5), waits like a computation, and replies with re = x, im = y,
// e = 0x01020304, flags = 0x01 (or 0x80 for a bad checksum). rx_TREADY is
// throttled to exercise back-pressure through the FIFOs.
module g_uart_kernel (
    input  wire       ap_clk,
    input  wire       ap_rst_n,
    input  wire [7:0] rx_TDATA,
    input  wire       rx_TVALID,
    output wire       rx_TREADY,
    output reg  [7:0] tx_TDATA,
    output reg        tx_TVALID,
    input  wire       tx_TREADY
);
    localparam [1:0] S_RX = 2'd0, S_BUSY = 2'd1, S_TX = 2'd2;
    reg [1:0]   state;
    reg [3:0]   nrx;          // bytes of the current request received
    reg [7:0]   req [0:9];
    reg [7:0]   rep [0:14];
    reg [3:0]   ntx;
    reg [11:0]  delay;
    reg         throttle;
    integer     i;
    reg [7:0]   chk;

    assign rx_TREADY = (state == S_RX) && throttle;

    always @(posedge ap_clk) begin
        if (!ap_rst_n) begin
            state <= S_RX; nrx <= 0; ntx <= 0; delay <= 0; throttle <= 1'b0;
            tx_TVALID <= 1'b0; tx_TDATA <= 8'h00;
        end else begin
            throttle <= ~throttle;
            case (state)
                S_RX:
                    if (rx_TVALID && rx_TREADY) begin
                        if (nrx == 0 && rx_TDATA != 8'hA5) begin
                            // still hunting for the sync byte
                        end else begin
                            req[nrx] <= rx_TDATA;
                            if (nrx == 9) begin
                                nrx <= 0;
                                state <= S_BUSY;
                                delay <= 12'd600;
                            end else nrx <= nrx + 1'b1;
                        end
                    end
                S_BUSY:
                    if (delay == 0) begin
                        chk = 8'h00;
                        for (i = 1; i <= 8; i = i + 1) chk = chk ^ req[i];
                        rep[0] <= 8'h5A;
                        for (i = 0; i < 8; i = i + 1) rep[1 + i] <= req[1 + i];   // re = x, im = y
                        rep[9] <= 8'h04; rep[10] <= 8'h03; rep[11] <= 8'h02; rep[12] <= 8'h01;
                        rep[13] <= (chk == req[9]) ? 8'h01 : 8'h80;
                        state <= S_TX;
                        ntx <= 0;
                    end else delay <= delay - 1'b1;
                S_TX: begin
                    if (!tx_TVALID || tx_TREADY) begin
                        if (tx_TVALID && ntx == 4'd15) begin
                            tx_TVALID <= 1'b0;
                            state <= S_RX;
                        end else if (ntx < 4'd15) begin
                            if (ntx == 4'd14) begin
                                chk = 8'h00;
                                for (i = 1; i < 14; i = i + 1) chk = chk ^ rep[i];
                                tx_TDATA <= chk;
                            end else tx_TDATA <= rep[ntx];
                            tx_TVALID <= 1'b1;
                            ntx <= ntx + 1'b1;
                        end else begin
                            tx_TVALID <= 1'b0;
                            state <= S_RX;
                        end
                    end
                end
                default: state <= S_RX;
            endcase
        end
    end
endmodule
