// g_uart_emulator.cpp -- the HLS kernel as a desktop program speaking the same
// UART byte protocol on stdin/stdout, so the host client can be tested without
// a board:   python3 host/g_client.py --emulator build/g_uart_emulator --at 0.3,0.4
#include <cstdio>

#include "g_eval.h"

int main() {
    hls::stream<uint8_t> rx("rx"), tx("tx");
    int c;
    // feed bytes until a full request (sync + 9 bytes) is buffered, then run
    // one kernel invocation and flush its reply
    int pending = -1;  // bytes still needed for the current request; -1 = no sync yet
    while ((c = std::getchar()) != EOF) {
        uint8_t b = (uint8_t)c;
        if (pending < 0) {
            if (b != G_SYNC_IN) continue;
            rx.write(b);
            pending = 9;
            continue;
        }
        rx.write(b);
        if (--pending == 0) {
            g_uart_kernel(rx, tx);
            while (!tx.empty()) std::putchar(tx.read());
            std::fflush(stdout);
            pending = -1;
        }
    }
    return 0;
}
