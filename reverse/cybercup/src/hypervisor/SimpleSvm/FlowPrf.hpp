#pragma once





static inline unsigned __int64 HvFlowRotl64(unsigned __int64 value, unsigned shift)
{
    return (value << shift) | (value >> (64 - shift));
}

static inline void HvFlowSipRound(unsigned __int64& v0, unsigned __int64& v1,
                                  unsigned __int64& v2, unsigned __int64& v3)
{
    v0 += v1;
    v1 = HvFlowRotl64(v1, 13);
    v1 ^= v0;
    v0 = HvFlowRotl64(v0, 32);
    v2 += v3;
    v3 = HvFlowRotl64(v3, 16);
    v3 ^= v2;
    v0 += v3;
    v3 = HvFlowRotl64(v3, 21);
    v3 ^= v0;
    v2 += v1;
    v1 = HvFlowRotl64(v1, 17);
    v1 ^= v2;
    v2 = HvFlowRotl64(v2, 32);
}

static inline unsigned __int64 HvFlowSipHash24(unsigned __int64 k0,
                                                unsigned __int64 k1,
                                                unsigned __int64 m0,
                                                unsigned __int64 m1,
                                                unsigned __int64 m2)
{
    unsigned __int64 v0 = 0x736f6d6570736575ULL ^ k0;
    unsigned __int64 v1 = 0x646f72616e646f6dULL ^ k1;
    unsigned __int64 v2 = 0x6c7967656e657261ULL ^ k0;
    unsigned __int64 v3 = 0x7465646279746573ULL ^ k1;
    const unsigned __int64 blocks[4] = {m0, m1, m2, 24ULL << 56};
    for (unsigned i = 0; i < 4; ++i)
    {
        v3 ^= blocks[i];
        HvFlowSipRound(v0, v1, v2, v3);
        HvFlowSipRound(v0, v1, v2, v3);
        v0 ^= blocks[i];
    }
    v2 ^= 0xff;
    for (unsigned i = 0; i < 4; ++i)
        HvFlowSipRound(v0, v1, v2, v3);
    return v0 ^ v1 ^ v2 ^ v3;
}
