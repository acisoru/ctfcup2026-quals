// Minimal stand-in for Vitis HLS <hls_stream.h>, for building the C model and
// testbench with a plain C++ compiler. Vitis HLS uses its own header instead.
#pragma once
#include <cstddef>
#include <deque>
#include <stdexcept>

namespace hls {
template <typename T>
class stream {
    std::deque<T> q_;

public:
    stream() {}
    explicit stream(const char *) {}
    void write(const T &v) { q_.push_back(v); }
    T read() {
        if (q_.empty()) throw std::runtime_error("hls::stream: read from empty stream");
        T v = q_.front();
        q_.pop_front();
        return v;
    }
    bool empty() const { return q_.empty(); }
    std::size_t size() const { return q_.size(); }
};
}  // namespace hls
