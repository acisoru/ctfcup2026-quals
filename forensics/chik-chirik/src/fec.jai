RS_DATA :: 3;
RS_WIRE :: 7;

gf8_mul :: (left: u8, right: u8) -> u8 {
    a := left;
    b := right;
    result: u8;
    while b != 0 {
        if (b & 1) != 0 result ^= a;
        b >>= 1;
        a <<= 1;
        if (a & 8) != 0 a ^= 11;
    }
    return result;
}

rs_encode :: (data: [RS_DATA] u8) -> [RS_WIRE] u8 {
    code: [RS_WIRE] u8;
    for i: 0..RS_WIRE-1 {
        x := cast(u8) (i + 1);
        code[i] = data[0] ^ gf8_mul(data[1], x) ^ gf8_mul(data[2], gf8_mul(x, x));
    }
    return code;
}

crc32 :: (bytes: string) -> u32 {
    crc: u32 = 0xFFFFFFFF;
    for byte: bytes {
        crc ^= byte;
        for 0..7 {
            low := crc & 1;
            crc >>= 1;
            if low != 0 crc ^= 0xEDB88320;
        }
    }
    return crc ^ 0xFFFFFFFF;
}

make_wire_symbols :: (payload: string, initial: Generator) -> [] u8 {
    frame := NewArray(payload.count + 4, u8);
    defer array_reset(*frame);
    memcpy(frame.data, payload.data, payload.count);
    put_le(frame.data + payload.count, crc32(payload), 4);
    bits := frame.count * 8;
    blocks := (bits + RS_DATA - 1) / RS_DATA;
    source := NewArray(blocks * RS_DATA, u8);
    defer array_reset(*source);
    g := initial;
    previous: u8 = 0;
    for i: 0..bits-1 {
        u := next_bit(*g);
        v := next_bit(*g);
        h := next_bit(*g);
        plain := (frame[i / 8] >> (7 - i % 8)) & 1;
        phase := previous ^ plain ^ h;
        source[i] = (u << 2) | (v << 1) | phase;
        previous = phase;
    }

    wire := NewArray(blocks * RS_WIRE, u8);
    for block: 0..blocks-1 {
        data: [RS_DATA] u8;
        memcpy(data.data, source.data + block * RS_DATA, RS_DATA);
        code := rs_encode(data);
        memcpy(wire.data + block * RS_WIRE, code.data, RS_WIRE);
    }
    return wire;
}
