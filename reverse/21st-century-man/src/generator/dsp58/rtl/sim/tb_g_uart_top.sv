// tb_g_uart_top.sv -- Icarus/Vivado simulation of the UART plumbing
// (uart_rx -> FIFO -> kernel -> FIFO -> uart_tx) with the kernel stand-in.
`timescale 1ns / 1ps
module tb_g_uart_top;
    localparam integer CLK_HZ = 1_000_000;
    localparam integer BAUD   = 62_500;           // 16 clocks per bit
    localparam real    BIT_NS = 1.0e9 / BAUD;

    reg clk = 1'b0;
    reg rst_n = 1'b0;
    reg rxd = 1'b1;
    wire txd, overrun, ferr;
    always #500 clk = ~clk;                       // 1 MHz

    g_uart_top #(.CLK_HZ(CLK_HZ), .BAUD(BAUD)) dut (
        .clk(clk), .rst_n(rst_n), .uart_rxd(rxd), .uart_txd(txd),
        .rx_overrun(overrun), .rx_frame_err(ferr));

    // ---- host side: send bytes -------------------------------------------
    task send_byte(input [7:0] b);
        integer k;
        begin
            rxd = 1'b0; #(BIT_NS);
            for (k = 0; k < 8; k = k + 1) begin rxd = b[k]; #(BIT_NS); end
            rxd = 1'b1; #(BIT_NS);
        end
    endtask

    task send_request(input [31:0] x, input [31:0] y, input corrupt);
        reg [7:0] c;
        integer k;
        begin
            c = 8'h00;
            send_byte(8'hA5);
            for (k = 0; k < 4; k = k + 1) begin send_byte(x[8*k +: 8]); c = c ^ x[8*k +: 8]; end
            for (k = 0; k < 4; k = k + 1) begin send_byte(y[8*k +: 8]); c = c ^ y[8*k +: 8]; end
            send_byte(corrupt ? (c ^ 8'h55) : c);
        end
    endtask

    // ---- host side: receive bytes ----------------------------------------
    reg [7:0] got [0:63];
    integer ngot = 0;
    integer stop_errs = 0;
    initial begin : monitor
        reg [7:0] b;
        integer k;
        forever begin
            @(negedge txd);
            #(BIT_NS / 2);
            if (txd == 1'b0) begin
                for (k = 0; k < 8; k = k + 1) begin #(BIT_NS); b[k] = txd; end
                #(BIT_NS);
                if (txd !== 1'b1) stop_errs = stop_errs + 1;
                got[ngot] = b;
                ngot = ngot + 1;
            end
        end
    end

    // ---- checks ----------------------------------------------------------
    integer errors = 0;
    task check_reply(input integer base, input [31:0] x, input [31:0] y, input [7:0] flags);
        reg [7:0] c;
        integer k;
        begin
            if (got[base] !== 8'h5A) begin errors = errors + 1; $display("reply %0d: bad sync %h", base / 15, got[base]); end
            for (k = 0; k < 4; k = k + 1) begin
                if (got[base + 1 + k] !== x[8*k +: 8]) errors = errors + 1;
                if (got[base + 5 + k] !== y[8*k +: 8]) errors = errors + 1;
            end
            if ({got[base + 12], got[base + 11], got[base + 10], got[base + 9]} !== 32'h01020304) errors = errors + 1;
            if (got[base + 13] !== flags) begin errors = errors + 1; $display("reply %0d: flags %h, expected %h", base / 15, got[base + 13], flags); end
            c = 8'h00;
            for (k = 1; k < 14; k = k + 1) c = c ^ got[base + k];
            if (got[base + 14] !== c) begin errors = errors + 1; $display("reply %0d: bad checksum", base / 15); end
        end
    endtask

    initial begin
        #(5000);
        rst_n = 1'b1;
        #(20000);
        send_byte(8'h13);                                   // line noise
        send_request(32'h3FC00000, 32'hBE800000, 1'b0);     // x = 1.5, y = -0.25
        send_request(32'h3E99999A, 32'h3ECCCCCD, 1'b0);     // x = 0.3, y = 0.4 (sent back to back)
        send_request(32'h3F800000, 32'h00000000, 1'b1);     // corrupted checksum
        wait (ngot == 45 || $time > 64'd200_000_000);
        #(2 * BIT_NS);
        if (ngot != 45) begin errors = errors + 1; $display("got %0d reply bytes, expected 45", ngot); end
        else begin
            check_reply(0,  32'h3FC00000, 32'hBE800000, 8'h01);
            check_reply(15, 32'h3E99999A, 32'h3ECCCCCD, 8'h01);
            check_reply(30, 32'h3F800000, 32'h00000000, 8'h80);
        end
        if (stop_errs) begin errors = errors + 1; $display("%0d stop-bit errors on txd", stop_errs); end
        if (overrun) begin errors = errors + 1; $display("rx overrun"); end
        $display("%s: %0d reply bytes, %0d errors", errors ? "FAIL" : "PASS", ngot, errors);
        $finish;
    end
endmodule
