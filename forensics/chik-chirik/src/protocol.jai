#import "Basic";
#import "Math";
#import "File";
POSIX :: #import "POSIX";

SAMPLE_RATE :: 48000;
SYMBOL_SAMPLES :: 2048;
FADE_SAMPLES :: 64;
MAX_PAYLOAD_BYTES :: 4096;
SIGNAL_AMPLITUDE :: 0.35;
DEFAULT_NOISE_AMPLITUDE :: 0.015;
END_FREQUENCIES :: float64.[4000, 5000, 7000, 8000];
PERMUTATION :: u8.[2, 0, 3, 1];
PREAMBLE_KINDS :: u8.[2, 0, 3, 1, 1, 3, 0, 2];
PREAMBLE_POLARITIES :: u8.[0, 1, 0, 1, 1, 0, 1, 0];
CHIRP_TAU :: 6.283185307179586476925286766559;
BYTES_PER_SAMPLE :: 2;
SYMBOL_BYTES :: SYMBOL_SAMPLES * BYTES_PER_SAMPLE;
WAV_HEADER_BYTES :: 44;

Generator :: struct { words: [4] u32; }
Templates :: struct { values: [4][SYMBOL_SAMPLES] float64; }

#load "fec.jai";

flush_file :: (file: File) -> bool {
    return POSIX.fflush(file.handle) == 0;
}

fail :: (message: string) {
    print("Error: %\n", message);
    exit(1);
}

rotate_left :: (x: u32, n: u32) -> u32 {
    return (x << n) | (x >> (32 - n));
}

parity32 :: (x: u32) -> u8 {
    v := x;
    v ^= v >> 16;
    v ^= v >> 8;
    v ^= v >> 4;
    v ^= v >> 2;
    v ^= v >> 1;
    return cast(u8) (v & 1);
}

next_bit :: (g: *Generator) -> u8 {
    t := g.words[1] << 9;
    g.words[2] ^= g.words[0];
    g.words[3] ^= g.words[1];
    g.words[1] ^= g.words[2];
    g.words[0] ^= g.words[3];
    g.words[2] ^= t;
    g.words[3] = rotate_left(g.words[3], 11);
    return parity32(g.words[3] & 0xA361C95B) ^ parity32(g.words[1] & 0x7D284E13);
}

read_le :: (data: *u8, bytes: int) -> u64 {
    result: u64;
    for i: 0..bytes-1 result |= (cast(u64) data[i]) << (8 * i);
    return result;
}

put_le :: (data: *u8, value: u64, bytes: int) {
    for i: 0..bytes-1 data[i] = cast(u8)((value >> (8 * i)) & 255);
}

is_zero :: inline (g: Generator) -> bool {
    return (g.words[0] | g.words[1] | g.words[2] | g.words[3]) == 0;
}

random_generator :: () -> Generator {
    file, ok := file_open("/dev/urandom");
    if !ok fail("Cannot open /dev/urandom.");
    defer file_close(*file);

    bytes: [16] u8;
    read_ok, count := file_read(file, bytes.data, bytes.count);
    if !read_ok || count != bytes.count fail("Cannot read /dev/urandom.");

    g: Generator;
    for i: 0..3 g.words[i] = cast(u32) read_le(bytes.data + 4 * i, 4);
    if is_zero(g) g.words[0] = 1;
    return g;
}

make_templates :: (templates: *Templates) {
    duration := cast(float64) SYMBOL_SAMPLES / SAMPLE_RATE;
    for kind: 0..3 {
        slope := (END_FREQUENCIES[kind] - 6000.0) / duration;
        for n: 0..SYMBOL_SAMPLES-1 {
            t := cast(float64) n / SAMPLE_RATE;
            envelope: float64 = 1;
            if n < FADE_SAMPLES envelope = cast(float64) n / FADE_SAMPLES;
            else if n >= SYMBOL_SAMPLES - FADE_SAMPLES {
                envelope = cast(float64) (SYMBOL_SAMPLES - 1 - n) / FADE_SAMPLES;
            }
            phase := CHIRP_TAU * (6000.0 * t + 0.5 * slope * t * t);
            templates.values[kind][n] = envelope * cos(phase);
        }
    }
}

render_symbol :: (pcm: *u8, templates: *Templates, kind: u8, polarity: u8, noise_amplitude: float64) {
    sign := ifx polarity != 0 then -1.0 else 1.0;
    for n: 0..SYMBOL_SAMPLES-1 {
        sample := sign * SIGNAL_AMPLITUDE * templates.values[kind][n];
        noise := cast(float64) read_le(pcm + 2 * n, 2) / 32767.5 - 1.0;
        sample += noise_amplitude * noise;
        sample = clamp(sample, -1.0, 1.0);
        quantized := cast(s32) (sample * 32767.0);
        put_le(pcm + 2 * n, cast(u64) (quantized & 0xFFFF), 2);
    }
}

write_symbol :: (file: *File, random: File, templates: *Templates, kind: u8, polarity: u8, noise_amplitude: float64) -> bool {
    pcm: [SYMBOL_BYTES] u8;
    if noise_amplitude != 0 {
        ok, count := file_read(random, pcm.data, pcm.count);
        if !ok || count != pcm.count return false;
    }
    render_symbol(pcm.data, templates, kind, polarity, noise_amplitude);
    return file_write(file, pcm.data, pcm.count);
}

put_tag :: (data: *u8, tag: string) {
    memcpy(data, tag.data, tag.count);
}

make_wav_header :: (data_bytes: int) -> [WAV_HEADER_BYTES] u8 {
    h: [WAV_HEADER_BYTES] u8;
    put_tag(h.data +  0, "RIFF");
    put_le (h.data +  4, cast(u64) (WAV_HEADER_BYTES - 8 + data_bytes), 4);
    put_tag(h.data +  8, "WAVE");
    put_tag(h.data + 12, "fmt ");
    put_le (h.data + 16, 16, 4);
    put_le (h.data + 20, 1, 2);
    put_le (h.data + 22, 1, 2);
    put_le (h.data + 24, SAMPLE_RATE, 4);
    put_le (h.data + 28, SAMPLE_RATE * BYTES_PER_SAMPLE, 4);
    put_le (h.data + 32, BYTES_PER_SAMPLE, 2);
    put_le (h.data + 34, BYTES_PER_SAMPLE * 8, 2);
    put_tag(h.data + 36, "data");
    put_le (h.data + 40, cast(u64) data_bytes, 4);
    return h;
}

write_capture :: (path: string, payload: string, initial: Generator) -> bool {
    if is_zero(initial) return false;

    random, random_ok := file_open("/dev/urandom");
    if !random_ok return false;
    defer file_close(*random);

    wire := make_wire_symbols(payload, initial);
    defer array_reset(*wire);

    symbol_count := PREAMBLE_KINDS.count + wire.count;
    header := make_wav_header(symbol_count * SYMBOL_BYTES);

    file, ok := file_open(path, for_writing=true);
    if !ok return false;
    defer file_close(*file);

    if !file_write(*file, header.data, header.count) return false;

    templates: Templates;
    make_templates(*templates);

    for kind, i: PREAMBLE_KINDS {
        polarity := PREAMBLE_POLARITIES[i];
        if !write_symbol(*file, random, *templates, kind, polarity, DEFAULT_NOISE_AMPLITUDE) return false;
    }

    for label: wire {
        kind     := PERMUTATION[label >> 1];
        polarity := label & 1;
        if !write_symbol(*file, random, *templates, kind, polarity, DEFAULT_NOISE_AMPLITUDE) return false;
    }

    return flush_file(*file);
}
