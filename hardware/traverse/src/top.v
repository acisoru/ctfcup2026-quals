// traverse: UART flag checker for iCE40 HX1K (iCEstick)
// 12 MHz clock, 115200 8N1. Send the flag followed by '\n',
// the board answers 's' (success) or 'f' (fail).
`include "dfa.v"

module uart_rx #(parameter DIV = 104) (
    input            clk,
    input            rx,
    output reg [7:0] data,
    output reg       valid
);
    reg [1:0] sync = 2'b11;
    reg [7:0] cnt = 0;
    reg [3:0] bitn = 0;
    reg       busy = 0;
    reg [7:0] sh = 0;

    always @(posedge clk) begin
        sync  <= {sync[0], rx};
        valid <= 0;
        if (!busy) begin
            if (!sync[1]) begin
                busy <= 1;
                cnt  <= DIV / 2;
                bitn <= 0;
            end
        end else if (cnt != 0) begin
            cnt <= cnt - 1;
        end else begin
            cnt  <= DIV - 1;
            bitn <= bitn + 1;
            if (bitn == 0) begin
                if (sync[1]) busy <= 0;  // glitch, not a start bit
            end else if (bitn == 9) begin
                busy <= 0;
                if (sync[1]) begin
                    data  <= sh;
                    valid <= 1;
                end
            end else begin
                sh <= {sync[1], sh[7:1]};
            end
        end
    end
endmodule

module uart_tx #(parameter DIV = 104) (
    input        clk,
    input  [7:0] data,
    input        start,
    output       tx
);
    reg [9:0] sh = 10'h3ff;
    reg [7:0] cnt = 0;
    reg [3:0] left = 0;

    assign tx = sh[0];

    always @(posedge clk) begin
        if (left == 0) begin
            if (start) begin
                sh   <= {1'b1, data, 1'b0};
                left <= 10;
                cnt  <= DIV - 1;
            end
        end else if (cnt != 0) begin
            cnt <= cnt - 1;
        end else begin
            cnt  <= DIV - 1;
            sh   <= {1'b1, sh[9:1]};
            left <= left - 1;
        end
    end
endmodule

module top (
    input  clk,
    input  rx,
    output tx,
    output led
);
    wire [7:0] ch;
    wire       ch_valid;
    uart_rx urx (.clk(clk), .rx(rx), .data(ch), .valid(ch_valid));

    reg  [7:0] tx_data = 0;
    reg        tx_start = 0;
    uart_tx utx (.clk(clk), .data(tx_data), .start(tx_start), .tx(tx));

    reg [3:0] por = 0;
    (* fsm_encoding = "none" *) reg [7:0] state = 0;
    reg ok = 0;
    wire [7:0] next;
    dfa_next dn (.state(state), .ch(ch), .next(next));

    assign led = ok;

    always @(posedge clk) begin
        tx_start <= 0;
        if (por != 4'hf) begin
            por   <= por + 1;
            state <= `DFA_START;
        end else if (ch_valid) begin
            if (ch == 8'h0a) begin
                ok       <= state == `DFA_ACCEPT;
                tx_data  <= state == `DFA_ACCEPT ? "s" : "f";
                tx_start <= 1;
                state    <= `DFA_START;
            end else if (ch != 8'h0d) begin
                state <= next;
            end
        end
    end
endmodule
