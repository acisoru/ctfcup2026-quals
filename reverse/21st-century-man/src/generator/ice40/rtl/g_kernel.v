// g_kernel.v -- UART-framed evaluator of the text function g on an iCE40.
//
//   g(z) = prod_j (z - a_j) / ( c * prod_k (z - b_k)^m_k ),   z = x + i y
//
// Same byte protocol as the Versal design (dsp58/hls/g_eval.h):
//   request : 0xA5, x[4], y[4], xor(x[4], y[4])                         10 bytes
//   reply   : 0x5A, re[4], im[4], e[4] (int32), flags, xor(bytes 1..13)  15 bytes
//   g(x + iy) = (re + i im) * 2^e,  max(|re|, |im|) in [1, 2)
//   flags   : bit0 |g| < 1, bit1 pole (re = im = NaN), bit2 zero, bit7 bad checksum
//
// Arithmetic (no floating-point units; everything is fixed point):
//   * coordinates x, y, a_j, b_k are signed Q4.28 (inputs saturated to [-4, 4));
//     the differences z - a_j are therefore exact,
//   * a running product is a complex block-floating-point number
//     (re, im) * 2^e with Q2.30 mantissas and max(|re|, |im|) in [1, 2);
//     after each complex multiply (4 shift-add 32x32 multipliers, 32 cycles)
//     the 65-bit result is renormalised by a leading-one detector and a shifter,
//   * numerator N and denominator D are formed this way, then
//     g = N conj(D) / |D|^2 * (1/c): |D|^2 is normalised to [1, 2), its
//     reciprocal comes from a 61-cycle restoring divider, and two more
//     complex-times-real multiplies finish the job,
//   * |g| < 1  <=>  e <= -2  or  (e == -1 and re^2 + im^2 < 4).
//
// The coefficients live in block RAM (gen/rom.hex: one 32-bit word {im, re}
// per zero/pole, Q4.12 each, the zeros first, then the poles); the pole orders
// are a small logic table (gen/orders.vh).
`default_nettype none

module g_kernel (
    input  wire       clk,
    input  wire       rst_n,
    input  wire [7:0] rx_data,
    input  wire       rx_valid,
    output wire       rx_ready,
    output reg  [7:0] tx_data,
    output reg        tx_valid,
    input  wire       tx_ready
);
`include "params.vh"

`ifndef ROM_HEX
`define ROM_HEX "gen/rom.hex"
`endif

    localparam [7:0] SYNC_IN  = 8'hA5;
    localparam [7:0] SYNC_OUT = 8'h5A;
    localparam [7:0] F_INSIDE = 8'h01, F_POLE = 8'h02, F_ZERO = 8'h04, F_BAD = 8'h80;
    localparam integer EW = 16;                 // exponent width (|e| stays below 2^15)

    // ------------------------------------------------------------------ tables
    localparam integer N_ROM = N_ZEROS + N_POLES;
    localparam integer AW    = $clog2(N_ROM);
    // one 32-bit word {im, re} per zero/pole, both Q4.12: the low 16 bits of
    // the Q4.28 coordinate are zero (tools/scale_model.py quantises the model)
    reg [31:0] rom [0:N_ROM-1];
    initial $readmemh(`ROM_HEX, rom);
    reg [AW-1:0] raddr;
    reg [31:0]   rdata;
    always @(posedge clk) rdata <= rom[raddr];
    wire [31:0] coef_re = {rdata[15:0],  16'h0000};
    wire [31:0] coef_im = {rdata[31:16], 16'h0000};

    localparam integer PW = 10;                 // pole index width (up to 1023 poles)
    reg [PW-1:0] pole_idx;
    reg [7:0]    pole_order;
`include "orders.vh"

    // --------------------------------------------------------- helper functions
    // fp32 -> Q4.28, saturating to [-4, 4), truncating toward zero
    function [31:0] f2q;
        input [31:0] f;
        reg        s;
        reg [7:0]  e;
        reg [31:0] m, mag;
        begin
            s = f[31];
            e = f[30:23];
            m = {8'b0, 1'b1, f[22:0]};
            if (e == 8'd0)            mag = 32'd0;
            else if (e >= 8'd129)     mag = s ? 32'h80000000 : 32'h7fffffff;
            else if (e >= 8'd122)     mag = m << (e - 8'd122);
            else                      mag = m >> (8'd122 - e);
            f2q = s ? -mag : mag;
        end
    endfunction

    // Q2.30 -> fp32 (truncating)
    function [31:0] q2f;
        input [31:0] q;
        reg        s;
        reg [31:0] mag, nrm;
        reg [5:0]  p;
        integer    i;
        begin
            s   = q[31];
            mag = s ? -q : q;
            p   = 6'd0;
            for (i = 0; i < 32; i = i + 1)
                if (mag[i]) p = i[5:0];
            nrm = mag << (6'd31 - p);
            q2f = (mag == 32'd0) ? 32'd0 : {s, 8'd97 + {2'b0, p}, nrm[30:8]};
        end
    endfunction

    // position of the most significant set bit of a 65-bit value
    function [6:0] msb65;
        input [64:0] v;
        integer i;
        begin
            msb65 = 7'd0;
            for (i = 0; i < 65; i = i + 1)
                if (v[i]) msb65 = i[6:0];
        end
    endfunction

    // -------------------------------------------------------------- multiplier
    reg         mul_start;
    reg  [31:0] ma_r, ma_i, mb_r, mb_i;
    wire        mul_busy;
    wire [63:0] p1, p2, p3, p4;     // ar*br, ai*bi, ar*bi, ai*br (signed)
    cmul4 u_mul (
        .clk(clk), .start(mul_start),
        .ar(ma_r), .ai(ma_i), .br(mb_r), .bi(mb_i),
        .busy(mul_busy), .p1(p1), .p2(p2), .p3(p3), .p4(p4));

    // combine + renormalise (combinational, used right after the multiplier)
    reg         cmode;              // 0: (p1 - p2, p3 + p4)   1: (p1 + p2, p4 - p3)
    reg  [6:0]  nfrac;              // fractional bits of the products: 58 or 60
    wire [64:0] cr = cmode ? ({p1[63], p1} + {p2[63], p2}) : ({p1[63], p1} - {p2[63], p2});
    wire [64:0] ci = cmode ? ({p4[63], p4} - {p3[63], p3}) : ({p3[63], p3} + {p4[63], p4});
    wire [64:0] mag_r = cr[64] ? -cr : cr;
    wire [64:0] mag_i = ci[64] ? -ci : ci;
    wire [64:0] orv   = mag_r | mag_i;
    wire        nzero = (orv == 65'd0);
    wire [6:0]  npos  = msb65(orv);
    wire [6:0]  nsh   = npos - 7'd30;              // >= 0 for every operand range used here
    wire [64:0] shr   = mag_r >> nsh;
    wire [64:0] shi   = mag_i >> nsh;
    wire [31:0] nm_r  = cr[64] ? -shr[31:0] : shr[31:0];
    wire [31:0] nm_i  = ci[64] ? -shi[31:0] : shi[31:0];
    wire signed [EW-1:0] eadj = $signed({{(EW-7){1'b0}}, npos}) - $signed({{(EW-7){1'b0}}, nfrac});
    wire [64:0] psum  = {1'b0, p1} + {1'b0, p2};   // p1 + p2 when both are squares

    // -------------------------------------------------------------- registers
    reg [63:0] payload;
    reg [7:0]  chk;
    reg [2:0]  cnt;
    reg [31:0] xq, yq;
    reg [31:0] pr, pi;  reg signed [EW-1:0] pe;  // running product
    reg [31:0] nr, ni;  reg signed [EW-1:0] ne;  // numerator
    reg [31:0] dr, di;  reg signed [EW-1:0] de;  // denominator
    reg [31:0] tr, ti;                           // N * conj(D), normalised
    reg [31:0] d2m;                              // |D|^2 mantissa in [1, 2), Q2.30
    reg [31:0] gr, gi;  reg signed [EW-1:0] ge;  // result (ge accumulates the exponent terms)
    reg [7:0]  flags;
    reg        den;                              // 0: numerator loop, 1: denominator loop
    reg [AW-1:0] j;                              // factors done in the current loop
    reg [7:0]  rep;                              // repetitions done of the current pole
    reg [3:0]  obyte;                            // reply byte index

    // --------------------------------------------------------------- divider
    reg         div_start;
    wire        div_busy;
    wire [31:0] rcp;                // floor(2^60 / d2m): 1/d2m in Q2.30
    recip30 u_div (.clk(clk), .start(div_start), .d(d2m), .busy(div_busy), .q(rcp));

    reg [31:0] out_re, out_im;
    wire [103:0] reply = {flags, {{(32-EW){ge[EW-1]}}, ge}, out_im, out_re};   // reply bytes 1..13
    wire [7:0]   reply_chk = reply[7:0] ^ reply[15:8] ^ reply[23:16] ^ reply[31:24] ^ reply[39:32]
                           ^ reply[47:40] ^ reply[55:48] ^ reply[63:56] ^ reply[71:64]
                           ^ reply[79:72] ^ reply[87:80] ^ reply[95:88] ^ reply[103:96];

    localparam [4:0]
        S_SYNC    = 5'd0,  S_PAYLOAD = 5'd1,  S_CHK     = 5'd2,  S_CONV_X = 5'd3,  S_CONV_Y  = 5'd4,
        S_F_ADDR  = 5'd5,  S_F_SUB   = 5'd6,  S_F_MUL   = 5'd7,  S_F_NORM = 5'd8,  S_DEN_DONE = 5'd9,
        S_D2_MUL  = 5'd10, S_D2_NORM = 5'd11, S_T_MUL   = 5'd12, S_T_NORM = 5'd13, S_RECIP   = 5'd14,
        S_SC_MUL  = 5'd15, S_SC_DONE = 5'd16, S_G_MUL   = 5'd17, S_G_NORM = 5'd18, S_M2_MUL  = 5'd19,
        S_M2_DONE = 5'd20, S_OUT_RE  = 5'd21, S_OUT_IM  = 5'd22, S_REPLY  = 5'd23;
    reg [4:0] state;

    assign rx_ready = (state == S_SYNC) || (state == S_PAYLOAD) || (state == S_CHK);

    // the single fp32 -> fixed converter and the single fixed -> fp32 converter
    wire [31:0] conv_q = f2q(state == S_CONV_X ? payload[31:0] : payload[63:32]);
    wire [31:0] conv_f = q2f(state == S_OUT_RE ? gr : gi);

    always @(posedge clk) begin
        mul_start <= 1'b0;
        div_start <= 1'b0;
        if (!rst_n) begin
            state    <= S_SYNC;
            tx_valid <= 1'b0;
            tx_data  <= 8'd0;
            raddr    <= 0;
            pole_idx <= 0;
            flags    <= 8'd0;
        end else case (state)
            // ------------------------------------------------------ framing in
            S_SYNC: if (rx_valid && rx_data == SYNC_IN) begin
                cnt   <= 3'd0;
                chk   <= 8'd0;
                state <= S_PAYLOAD;
            end
            S_PAYLOAD: if (rx_valid) begin
                payload <= {rx_data, payload[63:8]};       // byte 0 ends up in bits 7:0
                chk     <= chk ^ rx_data;
                cnt     <= cnt + 3'd1;
                if (cnt == 3'd7) state <= S_CHK;
            end
            S_CHK: if (rx_valid) begin
                if (rx_data != chk) begin
                    flags  <= F_BAD;
                    out_re <= 32'd0;
                    out_im <= 32'd0;
                    ge     <= 0;
                    obyte  <= 4'd0;
                    state  <= S_REPLY;
                end else state <= S_CONV_X;
            end
            S_CONV_X: begin
                xq    <= conv_q;
                state <= S_CONV_Y;
            end
            S_CONV_Y: begin
                yq    <= conv_q;
                pr    <= 32'h40000000;                     // 1.0
                pi    <= 32'd0;
                pe    <= 0;
                flags <= 8'd0;
                den   <= 1'b0;
                j     <= 0;
                raddr <= 0;
                cmode <= 1'b0;
                nfrac <= 7'd58;
                state <= S_F_ADDR;
            end
            // ---------------- numerator prod (z - a_j), then denominator prod (z - b_k)^m_k
            S_F_ADDR: state <= S_F_SUB;                    // rdata valid next cycle
            S_F_SUB: begin
                ma_r <= pr;  ma_i <= pi;
                mb_r <= xq - coef_re;
                mb_i <= yq - coef_im;
                mul_start <= 1'b1;
                state <= S_F_MUL;
            end
            S_F_MUL: if (!mul_busy && !mul_start) state <= S_F_NORM;
            S_F_NORM: begin
                pr <= nm_r;
                pi <= nm_i;
                pe <= pe + eadj;
                if (!den) begin
                    if (nzero || j == N_ZEROS - 1) begin   // numerator done (nzero: z is a zero of g)
                        if (nzero) begin
                            flags <= flags | F_ZERO;
                            nr <= 32'd0; ni <= 32'd0; ne <= 0;
                        end else begin
                            nr <= nm_r; ni <= nm_i; ne <= pe + eadj;
                        end
                        pr <= 32'h40000000; pi <= 32'd0; pe <= 0;
                        den      <= 1'b1;
                        pole_idx <= 0;
                        rep      <= 8'd0;
                        raddr    <= N_ZEROS;
                        state    <= S_F_ADDR;
                    end else begin
                        j     <= j + 1'b1;
                        raddr <= raddr + 1'b1;
                        state <= S_F_ADDR;
                    end
                end else if (nzero) begin                  // z is a pole of g
                    flags <= flags | F_POLE;
                    state <= S_DEN_DONE;
                end else if (rep + 8'd1 == pole_order) begin
                    rep <= 8'd0;
                    if (pole_idx == N_POLES - 1) begin
                        dr <= nm_r; di <= nm_i; de <= pe + eadj;
                        state <= S_DEN_DONE;
                    end else begin
                        pole_idx <= pole_idx + 1'b1;
                        raddr    <= raddr + 1'b1;
                        state    <= S_F_ADDR;
                    end
                end else begin
                    rep   <= rep + 8'd1;
                    state <= S_F_ADDR;
                end
            end
            S_DEN_DONE: begin
                obyte <= 4'd0;
                if (flags & F_POLE) begin
                    out_re <= 32'h7fc00000; out_im <= 32'h7fc00000; ge <= 0;
                    flags  <= F_POLE;
                    state  <= S_REPLY;
                end else if (flags & F_ZERO) begin
                    out_re <= 32'd0; out_im <= 32'd0; ge <= 0;
                    flags  <= F_ZERO | F_INSIDE;
                    state  <= S_REPLY;
                end else begin                              // |D|^2 = dr^2 + di^2
                    ma_r <= dr; ma_i <= di; mb_r <= dr; mb_i <= di;
                    mul_start <= 1'b1;
                    ge <= ne - de - C_EXP;
                    state <= S_D2_MUL;
                end
            end
            // ------------------------------------------------ g = N conj(D) / |D|^2 / c
            S_D2_MUL: if (!mul_busy && !mul_start) state <= S_D2_NORM;
            S_D2_NORM: begin                                // psum in [1, 8], Q4.60 (bit 60 = 1.0)
                if (psum[63])      begin d2m <= psum[64:33]; ge <= ge - 3; end
                else if (psum[62]) begin d2m <= psum[63:32]; ge <= ge - 2; end
                else if (psum[61]) begin d2m <= psum[62:31]; ge <= ge - 1; end
                else               begin d2m <= psum[61:30];              end
                ma_r <= nr; ma_i <= ni; mb_r <= dr; mb_i <= di;
                cmode <= 1'b1;                              // N * conj(D)
                nfrac <= 7'd60;
                mul_start <= 1'b1;
                state <= S_T_MUL;
            end
            S_T_MUL: if (!mul_busy && !mul_start) state <= S_T_NORM;
            S_T_NORM: begin
                tr <= nm_r; ti <= nm_i; ge <= ge + eadj;
                div_start <= 1'b1;
                state <= S_RECIP;
            end
            S_RECIP: if (!div_busy && !div_start) begin     // sc = (1/d2m) * (1/c mantissa)
                ma_r <= rcp; ma_i <= 32'd0; mb_r <= C_MANT_INV; mb_i <= 32'd0;
                mul_start <= 1'b1;
                state <= S_SC_MUL;
            end
            S_SC_MUL: if (!mul_busy && !mul_start) state <= S_SC_DONE;
            S_SC_DONE: begin                                // sc = p1 as Q2.30, value in (0.25, 1]
                ma_r <= tr; ma_i <= ti; mb_r <= p1[61:30]; mb_i <= 32'd0;
                cmode <= 1'b0;
                mul_start <= 1'b1;
                state <= S_G_MUL;
            end
            S_G_MUL: if (!mul_busy && !mul_start) state <= S_G_NORM;
            S_G_NORM: begin
                gr <= nm_r; gi <= nm_i; ge <= ge + eadj;
                ma_r <= nm_r; ma_i <= nm_i; mb_r <= nm_r; mb_i <= nm_i;
                mul_start <= 1'b1;
                state <= S_M2_MUL;
            end
            S_M2_MUL: if (!mul_busy && !mul_start) state <= S_M2_DONE;
            S_M2_DONE: begin                                // |g| < 1 <=> (gr^2 + gi^2) 4^e < 1
                if (ge <= -2 || (ge == -1 && !psum[62] && !psum[63]))
                    flags <= F_INSIDE;
                else
                    flags <= 8'd0;
                state <= S_OUT_RE;
            end
            S_OUT_RE: begin
                out_re <= conv_f;
                state  <= S_OUT_IM;
            end
            S_OUT_IM: begin
                out_im <= conv_f;
                obyte  <= 4'd0;
                state  <= S_REPLY;
            end
            // ----------------------------------------------------- framing out
            S_REPLY: begin
                if (!tx_valid) begin
                    tx_valid <= 1'b1;
                    case (obyte)
                        4'd0:    tx_data <= SYNC_OUT;
                        4'd14:   tx_data <= reply_chk;
                        default: tx_data <= reply[8 * (obyte - 1) +: 8];
                    endcase
                end else if (tx_ready) begin
                    tx_valid <= 1'b0;
                    if (obyte == 4'd14) state <= S_SYNC;
                    obyte <= obyte + 4'd1;
                end
            end
            default: state <= S_SYNC;
        endcase
    end
endmodule

// Four parallel signed 32x32 -> 64 shift-add multipliers, 32 cycles.
//   p1 = ar*br, p2 = ai*bi, p3 = ar*bi, p4 = ai*br
// Two's-complement right-shifting scheme: at step i the multiplicand is added
// when bit i of the multiplier is set (subtracted for the sign bit, i = 31),
// then the 65-bit accumulator is shifted right arithmetically.
module cmul4 (
    input  wire        clk,
    input  wire        start,
    input  wire [31:0] ar, ai, br, bi,
    output wire        busy,
    output wire [63:0] p1, p2, p3, p4
);
    reg [5:0]  cnt;
    reg signed [32:0] xr, xi, nxr, nxi;   // multiplicands and their negatives
    reg [64:0] a1, a2, a3, a4;            // {sum[32:0], multiplier[31:0]}
    assign busy = (cnt != 6'd0);
    assign p1 = a1[63:0];
    assign p2 = a2[63:0];
    assign p3 = a3[63:0];
    assign p4 = a4[63:0];

    wire last = (cnt == 6'd1);
    wire signed [32:0] n1 = $signed(a1[64:32]) + (a1[0] ? (last ? nxr : xr) : 33'sd0);
    wire signed [32:0] n2 = $signed(a2[64:32]) + (a2[0] ? (last ? nxi : xi) : 33'sd0);
    wire signed [32:0] n3 = $signed(a3[64:32]) + (a3[0] ? (last ? nxr : xr) : 33'sd0);
    wire signed [32:0] n4 = $signed(a4[64:32]) + (a4[0] ? (last ? nxi : xi) : 33'sd0);

    initial cnt = 6'd0;
    always @(posedge clk) begin
        if (start) begin
            xr  <= {ar[31], ar};
            xi  <= {ai[31], ai};
            nxr <= -$signed({ar[31], ar});
            nxi <= -$signed({ai[31], ai});
            a1  <= {33'd0, br};
            a2  <= {33'd0, bi};
            a3  <= {33'd0, bi};
            a4  <= {33'd0, br};
            cnt <= 6'd32;
        end else if (cnt != 6'd0) begin
            a1  <= {n1[32], n1, a1[31:1]};
            a2  <= {n2[32], n2, a2[31:1]};
            a3  <= {n3[32], n3, a3[31:1]};
            a4  <= {n4[32], n4, a4[31:1]};
            cnt <= cnt - 6'd1;
        end
    end
endmodule

// q = floor(2^60 / d) by restoring division, 61 cycles.  For d in [2^30, 2^31)
// (Q2.30 of [1, 2)) the quotient is 1/d in Q2.30, in (2^29, 2^30].
module recip30 (
    input  wire        clk,
    input  wire        start,
    input  wire [31:0] d,
    output wire        busy,
    output reg  [31:0] q
);
    reg [6:0]  cnt;
    reg [32:0] rem;
    reg [31:0] dd;
    assign busy = (cnt != 7'd0);

    wire [32:0] sh  = {rem[31:0], cnt == 7'd61};   // numerator bits: a single 1 then zeros
    wire        ge  = (sh >= {1'b0, dd});
    wire [32:0] nxt = ge ? sh - {1'b0, dd} : sh;

    initial cnt = 7'd0;
    always @(posedge clk) begin
        if (start) begin
            dd  <= d;
            rem <= 33'd0;
            q   <= 32'd0;
            cnt <= 7'd61;
        end else if (cnt != 7'd0) begin
            rem <= nxt;
            q   <= {q[30:0], ge};
            cnt <= cnt - 7'd1;
        end
    end
endmodule
