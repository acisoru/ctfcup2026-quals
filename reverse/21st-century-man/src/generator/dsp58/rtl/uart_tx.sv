// uart_tx.sv -- 8N1 UART transmitter with an AXI-Stream byte input.
module uart_tx #(
    parameter integer CLK_HZ = 250_000_000,
    parameter integer BAUD   = 115_200
) (
    input  wire       clk,
    input  wire       rst_n,
    input  wire [7:0] s_tdata,
    input  wire       s_tvalid,
    output wire       s_tready,
    output reg        txd
);
    localparam integer DIV = CLK_HZ / BAUD;
    localparam integer CW  = $clog2(DIV + 1);

    reg [9:0]    sh;      // {stop, data[7:0], start}
    reg [3:0]    nbits;   // bits still to send after the current one
    reg [CW-1:0] cnt;
    reg          busy;

    assign s_tready = !busy;

    always @(posedge clk) begin
        if (!rst_n) begin
            txd   <= 1'b1;
            busy  <= 1'b0;
            sh    <= 10'h3ff;
            nbits <= 4'd0;
            cnt   <= 0;
        end else if (!busy) begin
            if (s_tvalid) begin
                sh    <= {1'b1, s_tdata, 1'b0};
                txd   <= 1'b0;   // start bit
                nbits <= 4'd9;
                cnt   <= DIV - 1;
                busy  <= 1'b1;
            end
        end else if (cnt == 0) begin
            if (nbits == 0) begin
                busy <= 1'b0;    // stop bit done; line idles high
            end else begin
                sh    <= {1'b1, sh[9:1]};
                txd   <= sh[1];
                nbits <= nbits - 1'b1;
                cnt   <= DIV - 1;
            end
        end else begin
            cnt <= cnt - 1'b1;
        end
    end
endmodule
