// uart_rx.v -- 8N1 UART receiver, mid-bit sampling, one-cycle valid per byte.
module uart_rx #(
    parameter integer CLK_HZ = 250_000_000,
    parameter integer BAUD   = 115_200
) (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       rxd,
    output reg  [7:0] m_tdata,
    output reg        m_tvalid,   // one-cycle pulse per received byte
    output reg        frame_err   // last byte had no stop bit (byte dropped)
);
    localparam integer DIV = CLK_HZ / BAUD;
    localparam integer CW  = $clog2(DIV + 1);
    localparam [1:0] S_IDLE = 2'd0, S_START = 2'd1, S_DATA = 2'd2, S_STOP = 2'd3;

    reg [2:0]    sync;            // metastability synchroniser
    wire         r = sync[2];
    reg [1:0]    state;
    reg [CW-1:0] cnt;
    reg [2:0]    bitn;
    reg [7:0]    sh;

    always @(posedge clk) begin
        if (!rst_n) begin
            sync      <= 3'b111;
            state     <= S_IDLE;
            cnt       <= 0;
            bitn      <= 0;
            sh        <= 8'h00;
            m_tdata   <= 8'h00;
            m_tvalid  <= 1'b0;
            frame_err <= 1'b0;
        end else begin
            sync     <= {sync[1:0], rxd};
            m_tvalid <= 1'b0;
            case (state)
                S_IDLE:
                    if (!r) begin            // start bit edge: go to its middle
                        state <= S_START;
                        cnt   <= DIV / 2;
                    end
                S_START:
                    if (cnt == 0) begin
                        if (!r) begin
                            state <= S_DATA;
                            cnt   <= DIV - 1;
                            bitn  <= 3'd0;
                        end else begin
                            state <= S_IDLE; // glitch
                        end
                    end else cnt <= cnt - 1'b1;
                S_DATA:
                    if (cnt == 0) begin
                        sh  <= {r, sh[7:1]}; // LSB first
                        cnt <= DIV - 1;
                        if (bitn == 3'd7) state <= S_STOP;
                        else bitn <= bitn + 1'b1;
                    end else cnt <= cnt - 1'b1;
                S_STOP:
                    if (cnt == 0) begin
                        state <= S_IDLE;
                        if (r) begin
                            m_tdata   <= sh;
                            m_tvalid  <= 1'b1;
                            frame_err <= 1'b0;
                        end else begin
                            frame_err <= 1'b1;
                        end
                    end else cnt <= cnt - 1'b1;
            endcase
        end
    end
endmodule
