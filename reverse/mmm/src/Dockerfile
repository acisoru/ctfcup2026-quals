FROM debian:bookworm-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends g++ cmake ninja-build binutils zip && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY CMakeLists.txt main.cpp sha256.h params.h ./

RUN cmake -S . -B out -G Ninja -DCMAKE_BUILD_TYPE=Release && \
    cmake --build out && \
    mkdir /pkg && \
    objcopy --remove-section .comment out/mmm /pkg/mmm && \
    chmod 755 /pkg/mmm && \
    touch -d @0 /pkg/mmm && \
    cd /pkg && zip -X /mmm.zip mmm
