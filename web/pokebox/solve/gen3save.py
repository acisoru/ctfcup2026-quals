#!/usr/bin/env python3
"""Minimal Gen III (Emerald) save builder.

Builds a 128 KiB .sav with a chosen trainer name and party nicknames, with
correct section ids, checksums and save index so the PokeBox parser accepts it.
Only the fields the parser reads are populated; everything else is zeroed.
"""
import struct

SECTION_SIZE = 0x1000
SECTIONS = 14
SAVE_SIZE = 0x20000

FOOTER_ID = 0x0FF4
FOOTER_CHECKSUM = 0x0FF6
FOOTER_SAVEIDX = 0x0FFC

CHECKSUM_BYTES = {
    0: 3884, 1: 3968, 2: 3968, 3: 3968, 4: 3848,
    5: 3968, 6: 3968, 7: 3968, 8: 3968, 9: 3968,
    10: 3968, 11: 3968, 12: 3968, 13: 2000,
}

TRAINER_NAME_OFF = 0x0000
PARTY_COUNT_OFF = 0x0234
PARTY_ARRAY_OFF = 0x0238
MON_SIZE = 100
MON_NICK_OFF = 0x08
MON_NICK_LEN = 10

# western charmap (encode direction)
CMAP = {}
for i, c in enumerate("0123456789"): CMAP[c] = 0xA1 + i
for i, c in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ"): CMAP[c] = 0xBB + i
for i, c in enumerate("abcdefghijklmnopqrstuvwxyz"): CMAP[c] = 0xD5 + i
for c, b in {" ": 0x00, "&": 0x2D, "+": 0x2E, "=": 0x35, ";": 0x36,
             "%": 0x5B, "(": 0x5C, ")": 0x5D, "<": 0x85, ">": 0x86,
             "!": 0xAB, "?": 0xAC, ".": 0xAD, "-": 0xAE, "'": 0xB4,
             ",": 0xB8, "/": 0xBA, ":": 0xF0}.items():
    CMAP[c] = b
TERM = 0xFF


def encode(text, length):
    """Encode text to charmap bytes, padded to `length`.

    A field of N bytes holds up to N characters. If the text is shorter than
    the field, a 0xFF terminator follows; a text that fills the field exactly
    uses all N bytes with no terminator (as the real games store max-length
    names). The parser stops at 0xFF or at the field width, whichever first.
    """
    out = bytearray()
    for ch in text:
        if ch not in CMAP:
            raise ValueError(f"char {ch!r} not in Gen3 charmap")
        out.append(CMAP[ch])
    if len(out) > length:
        raise ValueError(f"{text!r} too long for field of {length}")
    if len(out) < length:
        out.append(TERM)
    out += bytes([0x00]) * (length - len(out))
    return bytes(out[:length])


def random_level(i):
    return [57, 54, 52, 50, 48, 45][i % 6]


def gen3_checksum(data):
    acc = 0
    for i in range(0, len(data), 4):
        word = int.from_bytes(data[i:i + 4].ljust(4, b"\x00"), "little")
        acc = (acc + word) & 0xFFFFFFFF
    return ((acc & 0xFFFF) + (acc >> 16)) & 0xFFFF


MON_LEVEL_OFF = 84
MON_HP_OFF = 86
MON_MAXHP_OFF = 88


def build(trainer="RED", nicks=None, save_index=1, tid=12345,
          gender=0, play=(42, 13, 7), levels=None):
    nicks = nicks or []
    levels = levels or [random_level(i) for i in range(len(nicks))]
    # SaveBlock2 (section 0) logical bytes
    sb2 = bytearray(0xF80)
    sb2[TRAINER_NAME_OFF:TRAINER_NAME_OFF + 8] = encode(trainer, 8)
    sb2[0x08] = gender & 1
    struct.pack_into("<H", sb2, 0x0A, tid & 0xFFFF)   # visible trainer id
    struct.pack_into("<H", sb2, 0x0E, play[0] & 0xFFFF)  # hours
    sb2[0x10] = play[1] & 0xFF                            # minutes
    sb2[0x11] = play[2] & 0xFF                            # seconds

    # SaveBlock1 logical bytes (party count + per-mon nickname/level/hp)
    sb1 = bytearray(0xF80 * 4)
    sb1[PARTY_COUNT_OFF] = len(nicks)
    for i, nk in enumerate(nicks):
        base = PARTY_ARRAY_OFF + i * MON_SIZE
        sb1[base + MON_NICK_OFF:base + MON_NICK_OFF + MON_NICK_LEN] = \
            encode(nk, MON_NICK_LEN)
        lv = levels[i] if i < len(levels) else 50
        sb1[base + MON_LEVEL_OFF] = lv & 0xFF
        hp = 20 + lv * 2
        struct.pack_into("<H", sb1, base + MON_HP_OFF, hp)
        struct.pack_into("<H", sb1, base + MON_MAXHP_OFF, hp)

    # section_id -> logical content bytes (what the checksum covers lives here)
    content = {0: bytes(sb2)}
    for sid in range(1, 5):
        content[sid] = bytes(sb1[(sid - 1) * 0xF80:sid * 0xF80])
    for sid in range(5, SECTIONS):
        content[sid] = bytes(0xF80)

    # assemble one block of 14 sections
    block = bytearray()
    for sid in range(SECTIONS):
        sec = bytearray(SECTION_SIZE)
        c = content[sid]
        sec[0:len(c)] = c
        struct.pack_into("<H", sec, FOOTER_ID, sid)
        chk = gen3_checksum(bytes(sec[0:CHECKSUM_BYTES[sid]]))
        struct.pack_into("<H", sec, FOOTER_CHECKSUM, chk)
        struct.pack_into("<I", sec, FOOTER_SAVEIDX, save_index)
        block += sec

    save = bytearray(SAVE_SIZE)
    save[0:len(block)] = block          # block A (active, higher index)
    # block B left zeroed with save_index 0 -> A wins
    return bytes(save)


if __name__ == "__main__":
    import sys
    data = build(trainer="RED", nicks=["Sparky", "Bulby", "Fin"])
    out = sys.argv[1] if len(sys.argv) > 1 else "test.sav"
    open(out, "wb").write(data)
    print(f"wrote {out} ({len(data)} bytes)")
