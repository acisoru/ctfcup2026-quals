// axis_fifo.sv -- small synchronous AXI-Stream FIFO (DEPTH a power of two).
module axis_fifo #(
    parameter integer W     = 8,
    parameter integer DEPTH = 64
) (
    input  wire         clk,
    input  wire         rst_n,
    input  wire [W-1:0] s_tdata,
    input  wire         s_tvalid,
    output wire         s_tready,
    output wire [W-1:0] m_tdata,
    output wire         m_tvalid,
    input  wire         m_tready
);
    localparam integer AW = $clog2(DEPTH);

    reg [W-1:0] mem [0:DEPTH-1];
    reg [AW:0]  wp, rp;

    wire empty = (wp == rp);
    wire full  = (wp[AW] != rp[AW]) && (wp[AW-1:0] == rp[AW-1:0]);

    assign s_tready = !full;
    assign m_tvalid = !empty;
    assign m_tdata  = mem[rp[AW-1:0]];

    always @(posedge clk) begin
        if (!rst_n) begin
            wp <= 0;
            rp <= 0;
        end else begin
            if (s_tvalid && !full) begin
                mem[wp[AW-1:0]] <= s_tdata;
                wp <= wp + 1'b1;
            end
            if (m_tready && !empty) rp <= rp + 1'b1;
        end
    end
endmodule
