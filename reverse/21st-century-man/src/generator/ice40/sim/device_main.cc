// device_main.cc -- runs the C++ model of the bitstream (tools/bitstream2cxx.sh)
// as a serial device: the chip's uart_rxd / uart_txd pins are bit-banged with
// the real bit period (CLK_HZ / BAUD clocks per bit) and connected to a
// pseudo-terminal, so any serial client can open it like a real board:
//
//   ./device [--clk-hz 200000000] [--baud 921600] [--stdio] [--link path]
//
// Prints the pty's path (e.g. /dev/pts/7) on stdout, then serves until killed.
// --stdio talks on stdin/stdout instead (like dsp58/build/g_uart_emulator).
// --link path also creates a symlink to the pty at a fixed path.
//
// Build: g++ -std=c++17 -O2 -I <out_dir> -DDESIGN_TOP=<module> sim/device_main.cc <out_dir>/design.cc
#include <cxxrtl/cxxrtl.h>

#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <deque>
#include <string>

#include <fcntl.h>
#include <poll.h>
#include <pty.h>
#include <termios.h>
#include <unistd.h>

#include "design.h"

#ifndef DESIGN_TOP
#define DESIGN_TOP chip
#endif
#define CAT_(a, b) a##b
#define CAT(a, b) CAT_(a, b)
using design_t = cxxrtl_design::CAT(p_, DESIGN_TOP);

namespace {

struct Options {
    double clk_hz = 200e6;
    long baud = 921600;
    bool stdio = false;
    std::string link;
};

Options parse(int argc, char **argv) {
    Options o;
    for (int i = 1; i < argc; i++) {
        std::string a = argv[i];
        auto need = [&](const char *what) -> const char * {
            if (i + 1 >= argc) { std::fprintf(stderr, "%s needs a value\n", what); std::exit(2); }
            return argv[++i];
        };
        if (a == "--clk-hz") o.clk_hz = std::atof(need("--clk-hz"));
        else if (a == "--baud") o.baud = std::atol(need("--baud"));
        else if (a == "--stdio") o.stdio = true;
        else if (a == "--link") o.link = need("--link");
        else {
            std::fprintf(stderr, "usage: %s [--clk-hz N] [--baud N] [--stdio] [--link path]\n", argv[0]);
            std::exit(2);
        }
    }
    return o;
}

// 8N1 transmitter towards the chip's RX pin
struct HostTx {
    long div;
    std::deque<uint8_t> queue;
    int bit = -1;        // -1 idle, 0 start, 1..8 data, 9 stop
    long cnt = 0;
    uint16_t frame = 0;
    bool line = true;

    explicit HostTx(long d) : div(d) {}
    bool busy() const { return bit >= 0 || !queue.empty(); }
    void tick() {
        if (bit < 0) {
            if (queue.empty()) { line = true; return; }
            frame = (uint16_t)(0x200 | (queue.front() << 1));   // stop, data, start(0)
            queue.pop_front();
            bit = 0;
            cnt = 0;
        }
        line = (frame >> bit) & 1;
        if (++cnt == div) {
            cnt = 0;
            if (++bit > 9) bit = -1;
        }
    }
};

// 8N1 receiver on the chip's TX pin
struct HostRx {
    long div;
    int bit = -1;
    long cnt = 0;
    uint8_t data = 0;
    bool last = true;

    explicit HostRx(long d) : div(d) {}
    // returns true when a byte completed (in `out`)
    bool tick(bool line, uint8_t &out) {
        bool got = false;
        if (bit < 0) {
            if (last && !line) { bit = 0; cnt = div / 2; }   // start bit edge: aim at mid-bit
        } else if (--cnt <= 0) {
            cnt = div;
            if (bit == 0) {
                if (line) bit = -1;                         // glitch, not a start bit
                else bit = 1;
            } else if (bit <= 8) {
                data = (uint8_t)((data >> 1) | (line ? 0x80 : 0));
                if (bit == 8) {
                    out = data;
                    got = true;                             // don't wait for the stop bit
                    bit = 9;
                } else bit++;
            } else {
                bit = -1;
            }
        }
        last = line;
        return got;
    }
};

}  // namespace

int main(int argc, char **argv) {
    Options opt = parse(argc, argv);
    long div = (long)(opt.clk_hz / opt.baud + 0.5);
    if (div < 8) { std::fprintf(stderr, "clk/baud ratio %ld too small\n", div); return 2; }

    int fd_in, fd_out;
    if (opt.stdio) {
        fd_in = 0;
        fd_out = 1;
    } else {
        int master, slave;
        char name[256];
        if (openpty(&master, &slave, name, nullptr, nullptr) != 0) { perror("openpty"); return 1; }
        termios t;
        tcgetattr(slave, &t);
        cfmakeraw(&t);
        tcsetattr(slave, TCSANOW, &t);
        // keep the slave open so the master never sees EIO; clients open it by name
        fd_in = fd_out = master;
        if (!opt.link.empty()) {
            unlink(opt.link.c_str());
            if (symlink(name, opt.link.c_str()) != 0) perror("symlink");
        }
        std::printf("%s\n", name);
        std::fflush(stdout);
    }
    fcntl(fd_in, F_SETFL, fcntl(fd_in, F_GETFL) | O_NONBLOCK);

    design_t top;
    HostTx tx(div);
    HostRx rx(div);
    auto tick = [&](bool rxd) {
        top.p_uart__rxd.set<bool>(rxd);
        top.p_clk.set<bool>(false);
        top.step();
        top.p_clk.set<bool>(true);
        top.step();
        return top.p_uart__txd.get<bool>();
    };

    // let the power-on reset run with an idle line
    for (int i = 0; i < 256; i++) tick(true);
    std::fprintf(stderr, "device: %ld clocks per bit (%.0f Hz / %ld baud)%s\n",
                 div, opt.clk_hz, opt.baud, opt.stdio ? ", stdio" : "");

    // the device is considered idle after this many quiet clocks: then we block
    // for input instead of spinning the model
    const long grace = 4 * 1000 * 1000;
    long quiet = 0;
    uint8_t buf[256];
    for (;;) {
        // host -> device bytes
        pollfd pfd{fd_in, POLLIN, 0};
        int timeout = (tx.busy() || quiet < grace) ? 0 : -1;
        if (poll(&pfd, 1, timeout) > 0 && (pfd.revents & POLLIN)) {
            ssize_t n = read(fd_in, buf, sizeof buf);
            if (n > 0) {
                for (ssize_t i = 0; i < n; i++) tx.queue.push_back(buf[i]);
                quiet = 0;
            } else if (n == 0 && opt.stdio) {
                return 0;                                   // stdin closed
            } else if (n < 0 && errno != EAGAIN && errno != EINTR) {
                usleep(10000);                              // pty: no client connected
            }
        } else if (pfd.revents & (POLLHUP | POLLERR)) {
            usleep(10000);
        }
        // a slice of simulated time
        for (int i = 0; i < 2048; i++) {
            tx.tick();
            bool txd = tick(tx.line);
            uint8_t b;
            if (rx.tick(txd, b)) {
                if (write(fd_out, &b, 1) < 0 && errno != EAGAIN) { /* client gone */ }
                if (opt.stdio) std::fflush(stdout);
                quiet = 0;
            } else if (tx.busy() || !txd) {
                quiet = 0;
            } else {
                quiet++;
            }
        }
    }
}
