// tb_top.v -- drives g_top through its UART pins with the points of
// gen/vectors.txt and compares the replies with the double-precision reference.
//
//   iverilog -g2012 -I gen -DCLK_HZ=16000000 -DBAUD=1000000 -o tb sim/tb_top.v rtl/*.v
//   vvp tb +N=400 [+STRIDE=7] [+VECTORS=gen/vectors.txt] [+VERBOSE]
//   (+STRIDE=k takes every k-th vector, so a short run still covers all classes)
//
// A reply is accepted when its log2|g| is within TOL of the reference and its
// inside flag agrees (unless the reference itself is within TOL of the contour).
`timescale 1ns / 1ps
`default_nettype none

module tb_top;
`ifndef CLK_HZ
`define CLK_HZ 16_000_000
`endif
`ifndef BAUD
`define BAUD 1_000_000
`endif
    localparam integer CLK_HZ = `CLK_HZ;
    localparam integer BAUD   = `BAUD;
    localparam integer DIV    = CLK_HZ / BAUD;
    localparam real    TOL    = 1.0e-4;

    reg  clk = 1'b0;
    reg  rxd = 1'b1;
    wire txd;
    always #5 clk = ~clk;

    g_top #(.CLK_HZ(CLK_HZ), .BAUD(BAUD)) dut (.clk(clk), .uart_rxd(rxd), .uart_txd(txd));

    task send_byte(input [7:0] b);
        integer i;
        begin
            rxd = 1'b0;
            repeat (DIV) @(posedge clk);
            for (i = 0; i < 8; i = i + 1) begin
                rxd = b[i];
                repeat (DIV) @(posedge clk);
            end
            rxd = 1'b1;
            repeat (DIV) @(posedge clk);
        end
    endtask

    task recv_byte(output [7:0] b);
        integer i;
        begin
            @(negedge txd);
            repeat (DIV / 2) @(posedge clk);
            for (i = 0; i < 8; i = i + 1) begin
                repeat (DIV) @(posedge clk);
                b[i] = txd;
            end
            repeat (DIV) @(posedge clk);         // stop bit
        end
    endtask

    // IEEE-754 fp32 bit pattern -> real
    function real f32(input [31:0] b);
        real m;
        integer e;
        begin
            if (b[30:23] == 0) f32 = 0.0;
            else begin
                m = 1.0 + b[22:0] / 8388608.0;
                e = b[30:23] - 127;
                f32 = (b[31] ? -m : m) * (2.0 ** e);
            end
        end
    endfunction

    integer fd, n, i, k, nmax, stride, lineno, errors, flips, fails, maxbad;
    reg [31:0] xb, yb;
    real ref_l2, got_l2, err, worst;
    integer ref_in;
    reg [7:0] rb [0:14];
    reg [7:0] chk;
    reg [31:0] re_b, im_b, e_b;
    reg verbose;
    reg [1023:0] vectors;

    initial begin
        if (!$value$plusargs("N=%d", nmax)) nmax = 400;
        if (!$value$plusargs("STRIDE=%d", stride)) stride = 1;
        if (!$value$plusargs("VECTORS=%s", vectors)) vectors = "gen/vectors.txt";
        lineno = 0;
        verbose = $test$plusargs("VERBOSE");
        fd = $fopen(vectors, "r");
        if (fd == 0) begin
            $display("cannot open %0s", vectors);
            $finish;
        end
        repeat (100) @(posedge clk);
        n = 0; errors = 0; flips = 0; fails = 0; worst = 0.0;
        while (n < nmax && $fscanf(fd, "%h %h %f %d\n", xb, yb, ref_l2, ref_in) == 4) begin
            lineno = lineno + 1;
            if ((lineno - 1) % stride != 0) continue;
            // ---- request
            chk = 0;
            send_byte(8'hA5);
            for (i = 0; i < 4; i = i + 1) begin send_byte(xb[8*i +: 8]); chk = chk ^ xb[8*i +: 8]; end
            for (i = 0; i < 4; i = i + 1) begin send_byte(yb[8*i +: 8]); chk = chk ^ yb[8*i +: 8]; end
            send_byte(chk);
            // ---- reply
            for (i = 0; i < 15; i = i + 1) recv_byte(rb[i]);
            chk = 0;
            for (i = 1; i < 14; i = i + 1) chk = chk ^ rb[i];
            if (rb[0] != 8'h5A || chk != rb[14]) begin
                $display("vector %0d: bad frame (sync %02x, chk %02x vs %02x)", n, rb[0], chk, rb[14]);
                errors = errors + 1;
            end
            re_b = {rb[4], rb[3], rb[2], rb[1]};
            im_b = {rb[8], rb[7], rb[6], rb[5]};
            e_b  = {rb[12], rb[11], rb[10], rb[9]};
            // ---- compare
            if (ref_l2 > 1.0e299) begin                       // exact pole expected
                if (!(rb[13] & 8'h02)) begin
                    $display("vector %0d: expected POLE, flags %02x", n, rb[13]);
                    errors = errors + 1;
                end else if (verbose) $display("vector %0d: pole ok", n);
            end else if (ref_l2 < -1.0e299) begin             // exact zero expected
                if (!(rb[13] & 8'h04)) begin
                    $display("vector %0d: expected ZERO, flags %02x", n, rb[13]);
                    errors = errors + 1;
                end else if (verbose) $display("vector %0d: zero ok", n);
            end else begin
                got_l2 = $signed(e_b) + 0.5 * $ln(f32(re_b) * f32(re_b) + f32(im_b) * f32(im_b)) / $ln(2.0);
                err = got_l2 - ref_l2;
                if (err < 0) err = -err;
                if (err > worst) worst = err;
                if (err > TOL) begin
                    $display("vector %0d: x=%08x y=%08x log2|g| got %f ref %f (err %g)", n, xb, yb, got_l2, ref_l2, err);
                    errors = errors + 1;
                end
                if ((rb[13] & 8'h01) != ref_in[0] && (ref_l2 > TOL || ref_l2 < -TOL)) begin
                    $display("vector %0d: inside flag %0d but reference log2|g| = %f", n, rb[13] & 1, ref_l2);
                    flips = flips + 1;
                end
                if ((f32(re_b) >= 2.0 || f32(re_b) <= -2.0 || f32(im_b) >= 2.0 || f32(im_b) <= -2.0) ||
                    (f32(re_b) < 1.0 && f32(re_b) > -1.0 && f32(im_b) < 1.0 && f32(im_b) > -1.0)) begin
                    $display("vector %0d: mantissa not normalised: re %f im %f", n, f32(re_b), f32(im_b));
                    errors = errors + 1;
                end
                if (verbose) $display("vector %0d: log2|g| %f (ref %f) flags %02x", n, got_l2, ref_l2, rb[13]);
            end
            n = n + 1;
        end
        // ---- a corrupted request must be answered with the BADFRAME flag
        send_byte(8'hA5);
        for (i = 0; i < 8; i = i + 1) send_byte(8'h11);
        send_byte(8'h55);
        for (i = 0; i < 15; i = i + 1) recv_byte(rb[i]);
        if (rb[13] != 8'h80) begin
            $display("bad checksum request: flags %02x, expected 80", rb[13]);
            errors = errors + 1;
        end
        $display("%0d vectors: max |log2|g| error| = %g, %0d value/frame errors, %0d inside/outside disagreements",
                 n, worst, errors, flips);
        if (errors == 0 && flips == 0) $display("PASS"); else $display("FAIL");
        $finish;
    end
endmodule
