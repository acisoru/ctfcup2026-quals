#pragma once



typedef unsigned int ARM_VM_U32;
typedef unsigned long long ARM_VM_U64;
typedef signed int ARM_VM_S32;
typedef signed long long ARM_VM_S64;

enum { ARM_VM_MAX_WORDS = 64, ARM_VM_MAX_STEPS = 256 };

struct ARM_VM_STATE
{
    ARM_VM_U64 X[31];
    ARM_VM_U32 Pc;
    ARM_VM_U32 Steps;
    unsigned char N, Z, C, V;
};

static inline ARM_VM_U64 ArmVmRead(const ARM_VM_STATE* s, ARM_VM_U32 reg)
{
    return reg == 31 ? 0 : s->X[reg];
}

static inline void ArmVmWrite(ARM_VM_STATE* s, ARM_VM_U32 reg,
                              ARM_VM_U64 value)
{
    if (reg != 31) s->X[reg] = value;
}

static inline bool ArmVmCondition(const ARM_VM_STATE* s, ARM_VM_U32 cond)
{
    switch (cond)
    {
    case 0: return s->Z != 0;                  
    case 1: return s->Z == 0;                  
    case 2: return s->C != 0;                  
    case 3: return s->C == 0;                  
    case 4: return s->N != 0;                  
    case 5: return s->N == 0;                  
    case 6: return s->V != 0;                  
    case 7: return s->V == 0;                  
    case 8: return s->C != 0 && s->Z == 0;    
    case 9: return s->C == 0 || s->Z != 0;    
    case 10: return s->N == s->V;              
    case 11: return s->N != s->V;              
    case 12: return s->Z == 0 && s->N == s->V; 
    case 13: return s->Z != 0 || s->N != s->V; 
    default: return false;
    }
}



static inline ARM_VM_U32 ArmVmRun(const ARM_VM_U32* code, ARM_VM_U32 count,
                                  ARM_VM_STATE* state)
{
    if (!code || !state || count == 0 || count > ARM_VM_MAX_WORDS) return 1;
    ARM_VM_STATE s = *state;
    s.Pc = 0;
    s.Steps = 0;
    s.N = s.Z = s.C = s.V = 0;
    while (s.Pc < count)
    {
        if (s.Steps == ARM_VM_MAX_STEPS) return 2;
        ARM_VM_U32 word = code[s.Pc];
        ARM_VM_U32 rd = word & 31;
        ARM_VM_U32 rn = (word >> 5) & 31;
        ARM_VM_U32 rm = (word >> 16) & 31;
        ARM_VM_S64 next = static_cast<ARM_VM_S64>(s.Pc) + 1;
        ++s.Steps;

        if ((word & 0xff800000u) == 0xd2800000u ||
            (word & 0xff800000u) == 0xf2800000u)
        {
            ARM_VM_U32 shift = ((word >> 21) & 3) * 16;
            ARM_VM_U64 part = static_cast<ARM_VM_U64>((word >> 5) & 0xffff) << shift;
            ARM_VM_U64 value = (word & 0x20000000u)
                ? ((ArmVmRead(&s, rd) & ~(0xffffULL << shift)) | part)
                : part;
            ArmVmWrite(&s, rd, value); 
        }
        else if ((word & 0xffe0fc00u) == 0x8a000000u ||
                 (word & 0xffe0fc00u) == 0xaa000000u ||
                 (word & 0xffe0fc00u) == 0xca000000u)
        {
            ARM_VM_U64 a = ArmVmRead(&s, rn);
            ARM_VM_U64 b = ArmVmRead(&s, rm);
            ARM_VM_U64 value = (word & 0x40000000u) ? (a ^ b)
                : ((word & 0x20000000u) ? (a | b) : (a & b));
            ArmVmWrite(&s, rd, value); 
        }
        else if ((word & 0xffe0fc1fu) == 0xeb00001fu ||
                 (word & 0xffc0001fu) == 0xf100001fu)
        {
            ARM_VM_U64 a = ArmVmRead(&s, rn);
            ARM_VM_U64 b = ((word & 0xffc0001fu) == 0xf100001fu)
                ? static_cast<ARM_VM_U64>((word >> 10) & 0xfff)
                : ArmVmRead(&s, rm);
            ARM_VM_U64 result = a - b;
            s.N = static_cast<unsigned char>((result >> 63) & 1);
            s.Z = static_cast<unsigned char>(result == 0);
            s.C = static_cast<unsigned char>(a >= b);
            s.V = static_cast<unsigned char>((((a ^ b) & (a ^ result)) >> 63) & 1);
        }
        else if ((word & 0xfc000000u) == 0x14000000u)
        {
            ARM_VM_S32 delta = static_cast<ARM_VM_S32>(word << 6) >> 6;
            next = static_cast<ARM_VM_S64>(s.Pc) + delta; 
        }
        else if ((word & 0xff000010u) == 0x54000000u &&
                 (word & 15) < 14)
        {
            if (ArmVmCondition(&s, word & 15))
            {
                ARM_VM_S32 delta = static_cast<ARM_VM_S32>((word >> 5) << 13) >> 13;
                next = static_cast<ARM_VM_S64>(s.Pc) + delta; 
            }
        }
        else return 1;

        if (next < 0 || next > count) return 3;
        s.Pc = static_cast<ARM_VM_U32>(next);
    }
    *state = s;
    return 0;
}
