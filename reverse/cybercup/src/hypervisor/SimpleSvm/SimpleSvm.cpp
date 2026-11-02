








#define POOL_NX_OPTIN   1
#include "SimpleSvm.hpp"

#include <intrin.h>
#include <ntifs.h>
#include <bcrypt.h>
#include <stdarg.h>
#include "FlowPrf.hpp"
#include "ArmVm.hpp"

EXTERN_C DRIVER_INITIALIZE DriverEntry;
static DRIVER_UNLOAD SvDriverUnload;
static CALLBACK_FUNCTION SvPowerCallbackRoutine;
static VOID SvProcessNotify(HANDLE ParentId, HANDLE ProcessId, BOOLEAN Create);

EXTERN_C
VOID
_sgdt (
    _Out_ PVOID Descriptor
    );

_IRQL_requires_max_(DISPATCH_LEVEL)
_IRQL_requires_min_(PASSIVE_LEVEL)
_IRQL_requires_same_
DECLSPEC_NORETURN
EXTERN_C
VOID
NTAPI
SvLaunchVm (
    _In_ PVOID HostRsp
    );








typedef struct _PML4_ENTRY_2MB
{
    union
    {
        UINT64 AsUInt64;
        struct
        {
            UINT64 Valid : 1;               
            UINT64 Write : 1;               
            UINT64 User : 1;                
            UINT64 WriteThrough : 1;        
            UINT64 CacheDisable : 1;        
            UINT64 Accessed : 1;            
            UINT64 Reserved1 : 3;           
            UINT64 Avl : 3;                 
            UINT64 PageFrameNumber : 40;    
            UINT64 Reserved2 : 11;          
            UINT64 NoExecute : 1;           
        } Fields;
    };
} PML4_ENTRY_2MB, *PPML4_ENTRY_2MB,
  PDPT_ENTRY_2MB, *PPDPT_ENTRY_2MB;
static_assert(sizeof(PML4_ENTRY_2MB) == 8,
              "PML4_ENTRY_1GB Size Mismatch");




typedef struct _PD_ENTRY_2MB
{
    union
    {
        UINT64 AsUInt64;
        struct
        {
            UINT64 Valid : 1;               
            UINT64 Write : 1;               
            UINT64 User : 1;                
            UINT64 WriteThrough : 1;        
            UINT64 CacheDisable : 1;        
            UINT64 Accessed : 1;            
            UINT64 Dirty : 1;               
            UINT64 LargePage : 1;           
            UINT64 Global : 1;              
            UINT64 Avl : 3;                 
            UINT64 Pat : 1;                 
            UINT64 Reserved1 : 8;           
            UINT64 PageFrameNumber : 31;    
            UINT64 Reserved2 : 11;          
            UINT64 NoExecute : 1;           
        } Fields;
    };
} PD_ENTRY_2MB, *PPD_ENTRY_2MB;
static_assert(sizeof(PD_ENTRY_2MB) == 8,
              "PDE_ENTRY_2MB Size Mismatch");




#include <pshpack1.h>
typedef struct _DESCRIPTOR_TABLE_REGISTER
{
    UINT16 Limit;
    ULONG_PTR Base;
} DESCRIPTOR_TABLE_REGISTER, *PDESCRIPTOR_TABLE_REGISTER;
static_assert(sizeof(DESCRIPTOR_TABLE_REGISTER) == 10,
              "DESCRIPTOR_TABLE_REGISTER Size Mismatch");
#include <poppack.h>





typedef struct _SEGMENT_DESCRIPTOR
{
    union
    {
        UINT64 AsUInt64;
        struct
        {
            UINT16 LimitLow;        
            UINT16 BaseLow;         
            UINT32 BaseMiddle : 8;  
            UINT32 Type : 4;        
            UINT32 System : 1;      
            UINT32 Dpl : 2;         
            UINT32 Present : 1;     
            UINT32 LimitHigh : 4;   
            UINT32 Avl : 1;         
            UINT32 LongMode : 1;    
            UINT32 DefaultBit : 1;  
            UINT32 Granularity : 1; 
            UINT32 BaseHigh : 8;    
        } Fields;
    };
} SEGMENT_DESCRIPTOR, *PSEGMENT_DESCRIPTOR;
static_assert(sizeof(SEGMENT_DESCRIPTOR) == 8,
              "SEGMENT_DESCRIPTOR Size Mismatch");

typedef struct _SEGMENT_ATTRIBUTE
{
    union
    {
        UINT16 AsUInt16;
        struct
        {
            UINT16 Type : 4;        
            UINT16 System : 1;      
            UINT16 Dpl : 2;         
            UINT16 Present : 1;     
            UINT16 Avl : 1;         
            UINT16 LongMode : 1;    
            UINT16 DefaultBit : 1;  
            UINT16 Granularity : 1; 
            UINT16 Reserved1 : 4;   
        } Fields;
    };
} SEGMENT_ATTRIBUTE, *PSEGMENT_ATTRIBUTE;
static_assert(sizeof(SEGMENT_ATTRIBUTE) == 2,
              "SEGMENT_ATTRIBUTE Size Mismatch");





typedef struct _PML4E_TREE
{
    DECLSPEC_ALIGN(PAGE_SIZE) PDPT_ENTRY_2MB PdptEntries[512];
    DECLSPEC_ALIGN(PAGE_SIZE) PD_ENTRY_2MB PdEntries[512][512];
} PML4E_TREE, *PPML4E_TREE;

typedef struct _SHARED_VIRTUAL_PROCESSOR_DATA
{
    PVOID MsrPermissionsMap;
    PVOID PartitionAssistPage;
    UINT64 VmId;
    BOOLEAN UseHyperVDirectFlush;
    PVOID VpAssistMappings[64];
    UINT8 OriginalDirectHypercall[64];
    DECLSPEC_ALIGN(PAGE_SIZE) PML4_ENTRY_2MB Pml4Entries[512];
    DECLSPEC_ALIGN(PAGE_SIZE) PML4E_TREE Pml4eTrees[2];    
    
    
    DECLSPEC_ALIGN(PAGE_SIZE) PML4_ENTRY_2MB NptSplitEntries[2][512];
    DECLSPEC_ALIGN(PAGE_SIZE) UINT8 GuardPage[PAGE_SIZE];
    DECLSPEC_ALIGN(PAGE_SIZE) UINT8 AliasPage[PAGE_SIZE];
    DECLSPEC_ALIGN(PAGE_SIZE) UINT8 SourcePage[PAGE_SIZE];
    UINT64 GuardGpa;
    UINT64 AliasGpa;
    UINT64 SourceGpa;
} SHARED_VIRTUAL_PROCESSOR_DATA, *PSHARED_VIRTUAL_PROCESSOR_DATA;

typedef struct _VIRTUAL_PROCESSOR_DATA
{
    union
    {
        
        
        
        
        
        
        DECLSPEC_ALIGN(PAGE_SIZE) UINT8 HostStackLimit[KERNEL_STACK_SIZE];
        struct
        {
            UINT8 StackContents[KERNEL_STACK_SIZE - (sizeof(PVOID) * 6) - sizeof(KTRAP_FRAME)];
            KTRAP_FRAME TrapFrame;
            UINT64 GuestVmcbPa;     
            UINT64 HostVmcbPa;
            struct _VIRTUAL_PROCESSOR_DATA* Self;
            PSHARED_VIRTUAL_PROCESSOR_DATA SharedVpData;
            UINT64 Padding1;        
            UINT64 Reserved1;
        } HostStackLayout;
    };

    DECLSPEC_ALIGN(PAGE_SIZE) VMCB GuestVmcb;
    DECLSPEC_ALIGN(PAGE_SIZE) VMCB HostVmcb;
    DECLSPEC_ALIGN(PAGE_SIZE) UINT8 HostStateArea[PAGE_SIZE];
} VIRTUAL_PROCESSOR_DATA, *PVIRTUAL_PROCESSOR_DATA;
static_assert(sizeof(VIRTUAL_PROCESSOR_DATA) == KERNEL_STACK_SIZE + PAGE_SIZE * 3,
              "VIRTUAL_PROCESSOR_DATA Size Mismatch");

typedef struct _GUEST_REGISTERS
{
    UINT64 R15;
    UINT64 R14;
    UINT64 R13;
    UINT64 R12;
    UINT64 R11;
    UINT64 R10;
    UINT64 R9;
    UINT64 R8;
    UINT64 Rdi;
    UINT64 Rsi;
    UINT64 Rbp;
    UINT64 Rsp;
    UINT64 Rbx;
    UINT64 Rdx;
    UINT64 Rcx;
    UINT64 Rax;
} GUEST_REGISTERS, *PGUEST_REGISTERS;


EXTERN_C VOID SvForwardVmmcall(PGUEST_REGISTERS Registers, PUCHAR XmmState);
EXTERN_C UINT64 SvNptReadProbe(PVOID Page);
EXTERN_C VOID SvNptWriteProbe(PVOID Page, UINT64 Value);

EXTERN_C volatile LONG g_HvTrapAfterFlush = 0;
EXTERN_C volatile LONG g_HvLabCalls = 0;
EXTERN_C volatile LONG g_HvLabRejects = 0;
static volatile LONG g_HvFlowDirectSteps = 0;
static volatile LONG g_HvFlowUdSteps = 0;
static volatile LONG g_HvFlowBpSteps = 0;
static volatile LONG g_AcfLastSeed = 0;
static volatile LONG g_AcfLastMask = 0;
static volatile LONG g_AcfCalls = 0;
static PVOID g_NptProbePage = nullptr;
static volatile LONG g_NptReadHits = 0;
static volatile LONG g_NptWriteHits = 0;
static volatile LONG64 g_NptLastWrite = 0;
static volatile LONG g_NptAliasObservedLow = 0;

static UINT32 SvAcfHvMask(UINT32 seed)
{
    UINT32 v = seed ^ 0x9c3017a5u;
    v ^= v >> 16;
    v *= 0x7feb352du;
    v ^= v >> 15;
    v *= 0x846ca68bu;
    v ^= v >> 16;
    return v ^ 0x73d45bc1u ^
        static_cast<UINT32>(g_NptAliasObservedLow);
}




typedef struct _HV_LAB_SESSION
{
    volatile LONG State; 
                         
    UINT64 Cr3;
    UINT64 Token;
    UINT64 ExpiresAt;
} HV_LAB_SESSION;

static HV_LAB_SESSION g_HvLabSessions[128] = {};
static volatile LONG64 g_HvLabNextToken = 0;
static volatile LONG g_HvLabEnabled = 0;





typedef struct _HV_FLOW_SESSION
{
    volatile LONG State; 
    UINT64 Cr3;
    UINT64 Token;
    UINT64 Value;
    UINT64 Domain;
    UINT64 ExpiresAt;
    UINT64 TrapRip;
    UINT64 BreakRip;
    UINT32 NextStep;
    UINT32 PredicateUsed;
} HV_FLOW_SESSION;

static HV_FLOW_SESSION g_HvFlowSessions[64] = {};


static UINT64* g_HvFlowKey = nullptr;
static volatile LONG64 g_HvFlowSequence = 0;




static constexpr UINT32 kHvRouteSteps = 9;
typedef struct _HV_CHECK_SESSION
{
    volatile LONG State; 
    HANDLE ProcessId;
    UINT64 Cr3;
    UINT64 Token;
    UINT64 Value;
    UINT64 Domain;
    UINT64 ExpiresAt;
    UINT64 LastInput;
    UINT32 NextStep;
    UINT32 LastRoute;
} HV_CHECK_SESSION;

static HV_CHECK_SESSION g_HvCheckSessions[64] = {};
static volatile LONG64 g_HvCheckSequence = 0;



typedef struct _HV_ARM_SESSION
{
    volatile LONG State; 
    UINT64 Cr3;
    UINT64 Token;
    UINT64 ExpiresAt;
    UINT32 Count;
    UINT32 Ran;
    ARM_VM_U32 Code[ARM_VM_MAX_WORDS];
    ARM_VM_STATE Vm;
} HV_ARM_SESSION;

static HV_ARM_SESSION g_HvArmSessions[16] = {};
static volatile LONG64 g_HvArmSequence = 0;





typedef struct _HV_ARM_SITE
{
    volatile LONG State; 
    HANDLE ProcessId;
    UINT64 Cr3;
    UINT64 Rip;
    UINT64 Widths;
    UINT32 Count;
    UINT32 FlagMode; 
    ARM_VM_U32 Code[ARM_VM_MAX_WORDS];
} HV_ARM_SITE;

static HV_ARM_SITE g_HvArmSites[1024] = {};
static volatile LONG g_HvArmSiteRegistration = 0;




typedef struct _HV_ADDRESS_GATE
{
    volatile LONG State; 
    HANDLE ProcessId;
    UINT64 Cr3;
    UINT64 DecoyRip;
    UINT64 TargetRip;
    UINT64 FaultVa; 
    UINT32 Mode;
} HV_ADDRESS_GATE;

static HV_ADDRESS_GATE g_HvAddressGates[512] = {};
static volatile LONG g_HvAddressGateRegistration = 0;
static volatile LONG g_HvAddressGatePfHits = 0;
static volatile LONG g_HvAddressGateUdHits = 0;




static VOID SvProcessNotify(HANDLE ParentId, HANDLE ProcessId, BOOLEAN Create)
{
    UNREFERENCED_PARAMETER(ParentId);
    if (Create) return;
    for (auto& site : g_HvArmSites)
    {
        if (site.ProcessId == ProcessId &&
            InterlockedCompareExchange(&site.State, 1, 2) == 2)
        {
            site.ProcessId = nullptr;
            site.Cr3 = 0;
            site.Rip = 0;
            site.Widths = 0;
            site.Count = 0;
            site.FlagMode = 0;
            RtlSecureZeroMemory(site.Code, sizeof(site.Code));
            MemoryBarrier();
            InterlockedExchange(&site.State, 0);
        }
    }
    for (auto& gate : g_HvAddressGates)
    {
        if (gate.ProcessId == ProcessId &&
            InterlockedCompareExchange(&gate.State, 1, 2) == 2)
        {
            gate.ProcessId = nullptr;
            gate.Cr3 = 0;
            gate.DecoyRip = 0;
            gate.TargetRip = 0;
            gate.FaultVa = 0;
            gate.Mode = 0;
            MemoryBarrier();
            InterlockedExchange(&gate.State, 0);
        }
    }
    for (auto& session : g_HvCheckSessions)
    {
        if (session.ProcessId == ProcessId &&
            InterlockedCompareExchange(&session.State, 6, 2) == 2)
        {
            RtlSecureZeroMemory(reinterpret_cast<PUCHAR>(&session) +
                sizeof(session.State), sizeof(session) - sizeof(session.State));
            MemoryBarrier();
            InterlockedExchange(&session.State, 0);
        }
    }
}

static UINT64 SvRotateRight64(UINT64 value, UINT32 count)
{
    return (value >> count) | (value << (64 - count));
}

static bool SvHvAddressGateBind(UINT64 cr3, UINT64 decoy,
                                UINT64 encoded, UINT64 key, UINT32 mode,
                                UINT64 faultVa = 0)
{
    HANDLE processId = PsGetCurrentProcessId();
    constexpr UINT64 multiplier = 0x9e3779b97f4a7c15ULL;
    UINT64 operand = mode == 3 ? faultVa : decoy;
    UINT64 target = SvRotateRight64((encoded ^ key) - operand * multiplier, 17);
    if (InterlockedCompareExchange(&g_HvLabEnabled, 0, 0) == 0 ||
        (mode != 1 && mode != 2 && mode != 3) ||
        decoy < 0x10000 || decoy > 0x00007fffffffffffULL ||
        (mode == 3 && (faultVa < 0x10000 ||
                       faultVa > 0x00007fffffffffffULL || faultVa == decoy)) ||
        target < 0x10000 || target > 0x00007fffffffffffULL ||
        target == operand)
        return false;
    bool locked = false;
    for (UINT32 attempt = 0; attempt < 1024; ++attempt)
    {
        if (InterlockedCompareExchange(&g_HvAddressGateRegistration, 1, 0) == 0)
        {
            locked = true;
            break;
        }
        _mm_pause();
    }
    if (!locked) return false;
    bool bound = false;
    for (auto& gate : g_HvAddressGates)
        if (InterlockedCompareExchange(&gate.State, 0, 0) == 2 &&
            gate.ProcessId == processId && gate.Cr3 == cr3 &&
            gate.DecoyRip == decoy)
        {
            bound = gate.TargetRip == target && gate.Mode == mode &&
                gate.FaultVa == faultVa;
            goto done;
        }
    for (auto& gate : g_HvAddressGates)
        if (InterlockedCompareExchange(&gate.State, 0, 0) == 0)
        {
            InterlockedExchange(&gate.State, 1);
            gate.ProcessId = processId;
            gate.Cr3 = cr3;
            gate.DecoyRip = decoy;
            gate.TargetRip = target;
            gate.FaultVa = faultVa;
            gate.Mode = mode;
            MemoryBarrier();
            InterlockedExchange(&gate.State, 2);
            bound = true;
            break;
        }
done:
    InterlockedExchange(&g_HvAddressGateRegistration, 0);
    return bound;
}

static bool SvHvAddressGateLookup(UINT64 cr3, UINT64 decoy, UINT32 mode,
                                  UINT64* target, UINT64 faultVa = 0)
{
    HANDLE processId = PsGetCurrentProcessId();
    for (const auto& gate : g_HvAddressGates)
        if (InterlockedCompareExchange(const_cast<volatile LONG*>(&gate.State),
                                       0, 0) == 2 &&
            gate.ProcessId == processId && gate.Cr3 == cr3 &&
            gate.DecoyRip == decoy && gate.Mode == mode &&
            gate.FaultVa == faultVa)
        {
            *target = gate.TargetRip;
            return true;
        }
    return false;
}

static bool SvHvArmWidthsValid(UINT64 widths)
{
    if (widths == 0 || (widths >> 48) != 0) return false;
    for (UINT32 i = 0; i < 16; ++i)
        if (((widths >> (i * 3)) & 7) > 4) return false;
    return true;
}

static bool SvHvArmBind(UINT64 cr3, UINT64 rip, UINT64 widths,
                        const ARM_VM_U32* code, UINT32 count,
                        UINT32 flagMode)
{
    HANDLE processId = PsGetCurrentProcessId();
    if (rip < 0x10000 || rip > 0x00007fffffffffffULL ||
        !SvHvArmWidthsValid(widths) || count == 0 ||
        count > ARM_VM_MAX_WORDS || flagMode > 1)
        return false;
    if (flagMode == 1)
    {
        UINT32 outputs = 0;
        for (UINT32 i = 0; i < 16; ++i)
        {
            UINT32 width = static_cast<UINT32>((widths >> (i * 3)) & 7);
            if (width != 0)
            {
                if (width != 3 && width != 4) return false;
                ++outputs;
            }
        }
        if (outputs != 1) return false;
    }
    bool locked = false;
    for (UINT32 attempt = 0; attempt < 1024; ++attempt)
    {
        if (InterlockedCompareExchange(&g_HvArmSiteRegistration, 1, 0) == 0)
        {
            locked = true;
            break;
        }
        _mm_pause();
    }
    if (!locked) return false;
    bool bound = false;
    for (auto& site : g_HvArmSites)
        if (InterlockedCompareExchange(&site.State, 0, 0) == 2 &&
            site.ProcessId == processId && site.Cr3 == cr3 &&
            site.Rip == rip)
        {
            bound = site.Widths == widths && site.Count == count &&
                site.FlagMode == flagMode &&
                RtlCompareMemory(site.Code, code, count * sizeof(code[0])) ==
                    count * sizeof(code[0]);
            goto done;
        }
    for (auto& site : g_HvArmSites)
    {
        if (InterlockedCompareExchange(&site.State, 1, 0) != 0) continue;
        site.ProcessId = processId;
        site.Cr3 = cr3;
        site.Rip = rip;
        site.Widths = widths;
        site.Count = count;
        site.FlagMode = flagMode;
        RtlCopyMemory(site.Code, code, count * sizeof(code[0]));
        InterlockedExchange(&site.State, 2);
        bound = true;
        break;
    }
done:
    InterlockedExchange(&g_HvArmSiteRegistration, 0);
    return bound;
}

static VOID SvHvArmFree(HV_ARM_SESSION* session)
{
    
    RtlSecureZeroMemory(&session->Code, sizeof(session->Code));
    RtlSecureZeroMemory(&session->Vm, sizeof(session->Vm));
    session->Count = 0;
    session->Ran = 0;
    session->Cr3 = 0;
    session->Token = 0;
    session->ExpiresAt = 0;
    InterlockedExchange(&session->State, 0);
}

static UINT64 SvHvArmCall(UINT64 cr3, UINT64 site, UINT64 input,
                          UINT64 extra, UINT64 token, UINT64 guestRax,
                          UINT64* status)
{
    constexpr UINT64 timeout = 30ULL * 1000 * 1000 * 10;
    UINT64 now = KeQueryInterruptTime();
    if (InterlockedCompareExchange(&g_HvLabEnabled, 0, 0) == 0)
        return MAXUINT64;
    if (site == 0x31ff && input == 0 && extra == 0 && token == 0)
        return 0x00020000ULL;
    if (site == 0x3100 && input == 0 && extra == 0 && token == 0)
    {
        for (auto& session : g_HvArmSessions)
        {
            if (InterlockedCompareExchange(&session.State, 0, 0) == 2 &&
                now >= session.ExpiresAt &&
                InterlockedCompareExchange(&session.State, 6, 2) == 2)
                SvHvArmFree(&session);
            if (InterlockedCompareExchange(&session.State, 1, 0) != 0)
                continue;
            UINT64 sequence = static_cast<UINT64>(
                InterlockedIncrement64(&g_HvArmSequence));
            UINT64 next = HvFlowSipHash24(g_HvFlowKey[0], g_HvFlowKey[1],
                                           sequence, cr3, 0x41524d564d303031ULL);
            session.Cr3 = cr3;
            session.Token = next == 0 || next == MAXUINT64 ? next ^ 0x42 : next;
            session.ExpiresAt = now + timeout;
            session.Count = 0;
            session.Ran = 0;
            RtlZeroMemory(&session.Vm, sizeof(session.Vm));
            InterlockedExchange(&session.State, 2);
            return session.Token;
        }
        return MAXUINT64;
    }
    if (token == 0 || token == MAXUINT64 || site < 0x3101 || site > 0x3106)
        return MAXUINT64;
    for (auto& session : g_HvArmSessions)
    {
        if (InterlockedCompareExchange(&session.State, 0, 0) != 2 ||
            session.Cr3 != cr3 || session.Token != token)
            continue;
        if (InterlockedCompareExchange(&session.State, 3, 2) != 2)
            return MAXUINT64;
        if (session.Cr3 != cr3 || session.Token != token)
        {
            InterlockedExchange(&session.State, 2);
            return MAXUINT64;
        }
        if (now >= session.ExpiresAt)
        {
            SvHvArmFree(&session);
            return MAXUINT64;
        }
        UINT64 result = MAXUINT64;
        if (site == 0x3101 && session.Ran == 0 &&
            extra == 0 && input <= MAXUINT32 &&
            session.Count < ARM_VM_MAX_WORDS)
        {
            session.Code[session.Count++] = static_cast<UINT32>(input);
            result = session.Count;
        }
        else if (site == 0x3102 && session.Ran == 0 && input < 31)
        {
            session.Vm.X[input] = extra;
            result = 0;
        }
        else if (site == 0x3103 && input == 0 && extra == 0 &&
                 session.Ran == 0 && session.Count != 0)
        {
            ARM_VM_U32 runStatus = ArmVmRun(session.Code, session.Count,
                                             &session.Vm);
            result = runStatus == 0 ? 0 : (0x8000000000000000ULL | runStatus);
            if (runStatus == 0) session.Ran = 1;
        }
        else if (site == 0x3105 && input == 0 && extra == 0 &&
                 session.Count != 0)
        {
            
            
            ARM_VM_STATE vm = session.Vm;
            vm.X[0] = guestRax;
            ARM_VM_U32 runStatus = ArmVmRun(session.Code, session.Count, &vm);
            session.Ran = 1; 
            if (runStatus == 0)
            {
                result = vm.X[0];
                *status = 0;
            }
            else
            {
                result = guestRax;
                *status = runStatus + 1; 
            }
        }
        else if (site == 0x3106 && session.Count != 0)
        {
            
            
            if (SvHvArmBind(cr3, input, extra, session.Code,
                            session.Count, 0))
            {
                session.Ran = 1;
                result = 0;
            }
        }
        else if (site == 0x3104 && input < 31 && extra == 0 &&
                 session.Ran != 0)
        {
            result = session.Vm.X[input];
            *status = 0; 
        }
        else if (site == 0x3104 && input == 31 && extra == 0)
        {
            SvHvArmFree(&session);
            return 0;
        }
        if (result != MAXUINT64 ||
            (site == 0x3104 && input < 31 && session.Ran != 0) ||
            site == 0x3105)
            session.ExpiresAt = now + timeout;
        InterlockedExchange(&session.State, 2);
        return result;
    }
    return MAXUINT64;
}

static UINT64 SvHvArmInlineWord(UINT64 word, UINT64 token, UINT64 extra,
                                UINT64 guestRax, UINT64 guestRbx,
                                UINT64* status)
{
    if (InterlockedCompareExchange(&g_HvLabEnabled, 0, 0) == 0 ||
        token != 0 || extra != 0 || word > MAXUINT32)
        return guestRax;
    ARM_VM_STATE vm = {};
    vm.X[0] = guestRax;
    vm.X[1] = guestRbx;
    ARM_VM_U32 instruction = static_cast<ARM_VM_U32>(word);
    ARM_VM_U32 runStatus = ArmVmRun(&instruction, 1, &vm);
    if (runStatus != 0)
    {
        *status = runStatus + 1;
        return guestRax;
    }
    *status = 0;
    return vm.X[0];
}



static UINT32 SvHvArmRunSite(UINT64 cr3, UINT64 rip,
                             PGUEST_REGISTERS regs,
                             PVIRTUAL_PROCESSOR_DATA vp)
{
    HANDLE processId = PsGetCurrentProcessId();
    for (const auto& site : g_HvArmSites)
    {
        if (InterlockedCompareExchange(const_cast<volatile LONG*>(&site.State),
                                       0, 0) != 2 ||
            site.ProcessId != processId || site.Cr3 != cr3 ||
            site.Rip != rip)
            continue;
        UINT64* guest[16] = {
            &regs->Rax, &regs->Rcx, &regs->Rdx, &regs->Rbx,
            &vp->GuestVmcb.StateSaveArea.Rsp, &regs->Rbp,
            &regs->Rsi, &regs->Rdi, &regs->R8, &regs->R9,
            &regs->R10, &regs->R11, &regs->R12, &regs->R13,
            &regs->R14, &regs->R15
        };
        ARM_VM_STATE vm = {};
        for (UINT32 i = 0; i < 16; ++i) vm.X[i] = *guest[i];
        if (ArmVmRun(site.Code, site.Count, &vm) != 0) return 2;
        for (UINT32 i = 0; i < 16; ++i)
        {
            UINT32 width = static_cast<UINT32>((site.Widths >> (i * 3)) & 7);
            if (width == 1) *guest[i] = (*guest[i] & ~0xffULL) | (vm.X[i] & 0xff);
            else if (width == 2) *guest[i] = (*guest[i] & ~0xffffULL) | (vm.X[i] & 0xffff);
            else if (width == 3) *guest[i] = vm.X[i] & 0xffffffffULL;
            else if (width == 4) *guest[i] = vm.X[i];
        }
        if (site.FlagMode == 1)
        {
            for (UINT32 i = 0; i < 16; ++i)
            {
                UINT32 width = static_cast<UINT32>((site.Widths >> (i * 3)) & 7);
                if (width == 0) continue;
                UINT64 value = width == 3 ? vm.X[i] & 0xffffffffULL : vm.X[i];
                UINT32 low = static_cast<UINT32>(value & 0xff);
                low ^= low >> 4;
                low ^= low >> 2;
                low ^= low >> 1;
                
                
                constexpr UINT64 changed = (1ULL << 0) | (1ULL << 2) |
                    (1ULL << 4) | (1ULL << 6) | (1ULL << 7) | (1ULL << 11);
                UINT64 flags = vp->GuestVmcb.StateSaveArea.Rflags & ~changed;
                if ((low & 1) == 0) flags |= 1ULL << 2;
                if (value == 0) flags |= 1ULL << 6;
                if ((value >> (width == 3 ? 31 : 63)) & 1) flags |= 1ULL << 7;
                vp->GuestVmcb.StateSaveArea.Rflags = flags;
                break;
            }
        }
        return 1;
    }
    return 0;
}



static bool SvHvArmQuickBind(UINT64 cr3, UINT64 nextRip, UINT64 kind,
                             UINT64 input, UINT64 descriptor, UINT64 delta)
{
    if (delta == 0 || delta > 64 ||
        (descriptor & ~0x3f0fULL) != 0) return false;
    UINT32 target = static_cast<UINT32>(descriptor & 15);
    UINT32 width = static_cast<UINT32>((descriptor >> 8) & 7);
    UINT32 flagMode = static_cast<UINT32>((descriptor >> 11) & 1);
    UINT32 op = static_cast<UINT32>((descriptor >> 12) & 3);
    if (width == 0 || width > 4) return false;
    UINT64 widths = static_cast<UINT64>(width) << (target * 3);
    ARM_VM_U32 code[5] = {};
    UINT32 count = 0;
    if (kind == 0x3201 && input <= MAXUINT32 && op == 0)
    {
        code[0] = static_cast<ARM_VM_U32>(input);
        count = 1;
    }
    else if ((kind == 0x3202 && flagMode == 0 && op == 0) ||
             (kind == 0x3203 && flagMode == 1 && op < 3))
    {
        UINT32 rd = kind == 0x3203 ? 16 : target;
        for (UINT32 hw = 0; hw < 4; ++hw)
        {
            UINT32 part = static_cast<UINT32>((input >> (hw * 16)) & 0xffff);
            code[hw] = (hw == 0 ? 0xd2800000u : 0xf2800000u) |
                       (hw << 21) | (part << 5) | rd;
        }
        count = 4;
        if (kind == 0x3203)
        {
            UINT32 base = op == 0 ? 0x8a000000u :
                          op == 1 ? 0xaa000000u : 0xca000000u;
            code[count++] = base | (16u << 16) | (target << 5) | target;
        }
    }
    if (count == 0) return false;
    return SvHvArmBind(cr3, nextRip + delta, widths, code, count, flagMode);
}

static UINT64 SvHvFlowToken(UINT64 value)
{
    
    return (value & 0x7ffffffffffffffdULL) | 2ULL;
}

static VOID SvHvCheckFree(HV_CHECK_SESSION* session)
{
    RtlSecureZeroMemory(reinterpret_cast<PUCHAR>(session) +
        sizeof(session->State), sizeof(*session) - sizeof(session->State));
    MemoryBarrier();
    InterlockedExchange(&session->State, 0);
}

static UINT64 SvHvCheckCall(UINT64 cr3, UINT64 site, UINT64 input,
                            UINT64 token)
{
    constexpr UINT64 timeout = 5ULL * 60 * 1000 * 1000 * 10;
    constexpr UINT64 openLabel = 0x434845434B4F504EULL;
    constexpr UINT64 stepLabel = 0x434845434B535445ULL;
    UINT64 now = KeQueryInterruptTime();
    HANDLE processId = PsGetCurrentProcessId();
    if (InterlockedCompareExchange(&g_HvLabEnabled, 0, 0) == 0 ||
        g_HvFlowKey == nullptr)
        return MAXUINT64;
    if (site == 0x305f && input == 0 && token == 0)
        return 0x00010000ULL;
    if (site == 0x3050 && input != 0 && token == 0)
    {
        for (auto& session : g_HvCheckSessions)
        {
            if (InterlockedCompareExchange(&session.State, 0, 0) == 2 &&
                now >= session.ExpiresAt &&
                InterlockedCompareExchange(&session.State, 6, 2) == 2)
                SvHvCheckFree(&session);
            if (InterlockedCompareExchange(&session.State, 1, 0) != 0)
                continue;
            UINT64 sequence = static_cast<UINT64>(
                InterlockedIncrement64(&g_HvCheckSequence));
            session.ProcessId = processId;
            session.Cr3 = cr3;
            session.Domain = input;
            session.Token = SvHvFlowToken(HvFlowSipHash24(
                g_HvFlowKey[0], g_HvFlowKey[1], sequence, cr3,
                input ^ openLabel));
            session.Value = HvFlowSipHash24(g_HvFlowKey[0], g_HvFlowKey[1],
                                            session.Token, cr3, input);
            session.ExpiresAt = now + timeout;
            session.LastInput = 0;
            session.NextStep = 0;
            session.LastRoute = 0;
            MemoryBarrier();
            InterlockedExchange(&session.State, 2);
            return session.Token;
        }
        return MAXUINT64;
    }
    if (token == 0 || token == MAXUINT64 ||
        !((site >= 0x3051 && site <= 0x3059) ||
          site == 0x305a || site == 0x305b))
        return MAXUINT64;
    for (auto& session : g_HvCheckSessions)
    {
        if (InterlockedCompareExchange(&session.State, 0, 0) != 2 ||
            session.ProcessId != processId || session.Cr3 != cr3 ||
            session.Token != token)
            continue;
        if (InterlockedCompareExchange(&session.State, 3, 2) != 2)
            return MAXUINT64;
        if (session.ProcessId != processId || session.Cr3 != cr3 ||
            session.Token != token || now >= session.ExpiresAt)
        {
            SvHvCheckFree(&session);
            return MAXUINT64;
        }
        if (site == 0x305b)
        {
            SvHvCheckFree(&session);
            return 0;
        }
        if (site == 0x305a)
        {
            UINT64 result = input == 0 &&
                session.NextStep == kHvRouteSteps ? 0 : MAXUINT64;
            SvHvCheckFree(&session);
            return result;
        }
        UINT32 index = static_cast<UINT32>(site - 0x3051);
        if (index + 1 == session.NextStep && input == session.LastInput)
        {
            UINT32 route = session.LastRoute;
            InterlockedExchange(&session.State, 2);
            return route;
        }
        if (index != session.NextStep || index >= kHvRouteSteps)
        {
            InterlockedExchange(&session.State, 2);
            return MAXUINT64;
        }
        UINT64 value = HvFlowSipHash24(g_HvFlowKey[0], g_HvFlowKey[1],
                                        session.Value, input,
                                        session.Domain ^
                                            (stepLabel + index));
        session.Value = value;
        session.LastInput = input;
        session.LastRoute = static_cast<UINT32>((value ^ (value >> 32)) & 3);
        session.NextStep++;
        session.ExpiresAt = now + timeout;
        UINT32 route = session.LastRoute;
        InterlockedExchange(&session.State, 2);
        return route;
    }
    return MAXUINT64;
}

static VOID SvHvFlowFree(HV_FLOW_SESSION* session)
{
    session->Cr3 = 0;
    session->Token = 0;
    session->Value = 0;
    session->Domain = 0;
    session->ExpiresAt = 0;
    session->TrapRip = 0;
    session->BreakRip = 0;
    session->NextStep = 0;
    session->PredicateUsed = 0;
    InterlockedExchange(&session->State, 0);
}

static UINT64 SvHvFlowCall(UINT64 cr3, UINT64 site, UINT64 input,
                            UINT64 token, UINT64 trapRip)
{
    constexpr UINT64 timeout = 5ULL * 60 * 1000 * 1000 * 10;
    constexpr UINT64 openLabel = 0x4846564c4f50454eULL;
    constexpr UINT64 stepLabel = 0x4846564c53544550ULL;
    constexpr UINT64 predicateLabel = 0x4856505245443031ULL;
    UINT64 now = KeQueryInterruptTime();

    if (InterlockedCompareExchange(&g_HvLabEnabled, 0, 0) == 0)
        return MAXUINT64;
    if (site == 0x30ff && input == 0 && token == 0)
        return 0x00010000ULL; 
    if (site == 0x30fe && input == 0 && token == 0)
        return 15; 

    if (site == 0x3000 && input != 0 && token == 0)
    {
        for (auto& session : g_HvFlowSessions)
        {
            LONG state = InterlockedCompareExchange(&session.State, 0, 0);
            if (state == 2 && now >= session.ExpiresAt &&
                InterlockedCompareExchange(&session.State, 6, 2) == 2)
            {
                if (now >= session.ExpiresAt)
                    SvHvFlowFree(&session);
                else
                    InterlockedExchange(&session.State, 2);
            }
            if (InterlockedCompareExchange(&session.State, 1, 0) == 0)
            {
                UINT64 sequence = static_cast<UINT64>(
                    InterlockedIncrement64(&g_HvFlowSequence));
                UINT64 next = HvFlowSipHash24(g_HvFlowKey[0], g_HvFlowKey[1],
                                               sequence, cr3, input ^ openLabel);
                session.Cr3 = cr3;
                session.Token = SvHvFlowToken(next);
                session.Value = HvFlowSipHash24(g_HvFlowKey[0], g_HvFlowKey[1],
                                                 session.Token, cr3, input);
                session.Domain = input;
                session.ExpiresAt = now + timeout;
                session.TrapRip = 0;
                session.BreakRip = 0;
                session.NextStep = 1;
                session.PredicateUsed = 0;
                InterlockedExchange(&session.State, 2);
                return session.Token;
            }
        }
        return MAXUINT64;
    }

    if (token == 0 || token == MAXUINT64 ||
        (site != 0x3001 && site != 0x3002 && site != 0x3003 &&
         site != 0x3010 && site != 0x3011 && site != 0x3021 &&
         site != 0x3030 && site != 0x3040 && site != 0x3041))
        return MAXUINT64;
    for (auto& session : g_HvFlowSessions)
    {
        if (InterlockedCompareExchange(&session.State, 0, 0) != 2 ||
            session.Cr3 != cr3 || session.Token != token)
            continue;
        if (InterlockedCompareExchange(&session.State, 3, 2) != 2)
            return MAXUINT64;
        if (session.Cr3 != cr3 || session.Token != token)
        {
            InterlockedExchange(&session.State, 2);
            return MAXUINT64;
        }
        if (now >= session.ExpiresAt)
        {
            SvHvFlowFree(&session);
            return MAXUINT64;
        }
        if (site == 0x3010)
        {
            
            
            
            if (trapRip != 0 || input < 0x10000 ||
                input >= 0x0000800000000000ULL || session.TrapRip != 0)
            {
                InterlockedExchange(&session.State, 2);
                return MAXUINT64;
            }
            session.TrapRip = input;
            InterlockedExchange(&session.State, 2);
            return 0;
        }
        if (site == 0x3040)
        {
            if (trapRip != 0 || input < 0x10000 ||
                input >= 0x0000800000000000ULL || session.BreakRip != 0)
            {
                InterlockedExchange(&session.State, 2);
                return MAXUINT64;
            }
            session.BreakRip = input;
            InterlockedExchange(&session.State, 2);
            return 0;
        }
        if (site == 0x3030)
        {
            if (trapRip != 0 || session.NextStep == 1 ||
                session.PredicateUsed != 0)
            {
                InterlockedExchange(&session.State, 2);
                return MAXUINT64;
            }
            UINT64 result = HvFlowSipHash24(
                g_HvFlowKey[0], g_HvFlowKey[1], session.Value,
                input ^ predicateLabel, session.Token);
            session.PredicateUsed = 1;
            session.ExpiresAt = now + timeout;
            InterlockedExchange(&session.State, 2);
            return result & 3;
        }
        if (site == 0x3011 &&
            (trapRip == 0 || session.TrapRip != trapRip))
        {
            InterlockedExchange(&session.State, 2);
            return MAXUINT64;
        }
        if (site == 0x3041 &&
            (trapRip == 0 || session.BreakRip != trapRip))
        {
            InterlockedExchange(&session.State, 2);
            return MAXUINT64;
        }
        if (site == 0x3021 && trapRip != MAXUINT64)
        {
            InterlockedExchange(&session.State, 2);
            return MAXUINT64;
        }
        if (site == 0x3003 || (site == 0x3002 && session.NextStep > 1))
        {
            SvHvFlowFree(&session);
            return 0;
        }
        if ((site != 0x3001 && site != 0x3011 &&
             site != 0x3021 && site != 0x3041) ||
            (input >> 32) != session.NextStep ||
            session.NextStep > 4)
        {
            InterlockedExchange(&session.State, 2);
            return MAXUINT64;
        }
        UINT64 value = HvFlowSipHash24(g_HvFlowKey[0], g_HvFlowKey[1],
                                        session.Value, input,
                                        session.Domain ^ session.Token);
        UINT64 next = SvHvFlowToken(HvFlowSipHash24(
            g_HvFlowKey[0], g_HvFlowKey[1], value, session.Token, stepLabel));
        if (next == session.Token)
            next ^= 4;
        session.Value = value;
        session.Token = next;
        session.TrapRip = 0;
        session.BreakRip = 0;
        session.NextStep++;
        session.PredicateUsed = 0;
        session.ExpiresAt = now + timeout;
        InterlockedExchange(&session.State, 2);
        if (site == 0x3001)
            InterlockedIncrement(&g_HvFlowDirectSteps);
        else if (site == 0x3011)
            InterlockedIncrement(&g_HvFlowUdSteps);
        else if (site == 0x3041)
            InterlockedIncrement(&g_HvFlowBpSteps);
        return next;
    }
    return MAXUINT64;
}

static UINT64 SvHvLabCalculate(UINT64 site, UINT64 input)
{
    UINT32 value = static_cast<UINT32>(input) ^ 0xa3c59ac3u;
    return ((value << 9) | (value >> 23)) +
        (static_cast<UINT32>(site) * 0x045d9f3bu);
}

static VOID SvHvLabFreeSession(HV_LAB_SESSION* session)
{
    session->Token = 0;
    session->Cr3 = 0;
    session->ExpiresAt = 0;
    InterlockedExchange(&session->State, 0);
}

static UINT64 SvHvLabCall(UINT64 cr3, UINT64 site, UINT64 input, UINT64 token)
{
    constexpr UINT64 timeout = 30ULL * 1000 * 1000 * 10; 
    UINT64 now = KeQueryInterruptTime();

    if (InterlockedCompareExchange(&g_HvLabEnabled, 0, 0) == 0)
        return MAXUINT64;
    if (site == 0)
        return 0x00020000ULL; 

    if (site == 1 && input == 0x2077 && token == 0)
    {
        for (auto& session : g_HvLabSessions)
        {
            LONG state = InterlockedCompareExchange(&session.State, 0, 0);
            if ((state == 2 || state == 4) && now >= session.ExpiresAt &&
                InterlockedCompareExchange(&session.State, 6, state) == state)
            {
                
                
                if (now >= session.ExpiresAt)
                    SvHvLabFreeSession(&session);
                else
                    InterlockedExchange(&session.State, state);
            }
            if (InterlockedCompareExchange(&session.State, 1, 0) == 0)
            {
                UINT64 next = static_cast<UINT64>(
                    InterlockedIncrement64(&g_HvLabNextToken));
                if (next == 0 || next == MAXUINT64)
                    next = static_cast<UINT64>(
                        InterlockedIncrement64(&g_HvLabNextToken));
                session.Cr3 = cr3;
                session.Token = next;
                session.ExpiresAt = now + timeout;
                InterlockedExchange(&session.State, 2);
                return next;
            }
        }
        return MAXUINT64;
    }

    if (token == 0 || token == MAXUINT64)
        return MAXUINT64;
    for (auto& session : g_HvLabSessions)
    {
        LONG state = InterlockedCompareExchange(&session.State, 0, 0);
        if (state != 2 && state != 4)
            continue;
        if (session.Token != token || session.Cr3 != cr3)
            continue;
        LONG busy = (site == 2) ? 6 :
            (site == 0x2077 && state == 2) ? 3 :
            (site == 0x2078 && state == 4) ? 5 : 0;
        if (busy == 0 || InterlockedCompareExchange(&session.State, busy, state) != state)
            return MAXUINT64;
        if (session.Token != token || session.Cr3 != cr3)
        {
            InterlockedExchange(&session.State, state);
            return MAXUINT64;
        }
        if (now >= session.ExpiresAt)
        {
            SvHvLabFreeSession(&session);
            return MAXUINT64;
        }
        if (site == 2)
        {
            SvHvLabFreeSession(&session);
            return 0;
        }
        if (site == 0x2077 && state == 2)
        {
            UINT64 result = SvHvLabCalculate(site, input);
            InterlockedExchange(&session.State, 4);
            return result;
        }
        if (site == 0x2078 && state == 4)
        {
            UINT64 result = SvHvLabCalculate(site, input);
            SvHvLabFreeSession(&session);
            return result;
        }
        return MAXUINT64;
    }
    return MAXUINT64;
}

typedef struct _GUEST_CONTEXT
{
    PGUEST_REGISTERS VpRegs;
    BOOLEAN ExitVm;
} GUEST_CONTEXT, *PGUEST_CONTEXT;





#define IA32_MSR_PAT    0x00000277
#define IA32_MSR_EFER   0xc0000080

#define EFER_SVME       (1UL << 12)

#define RPL_MASK        3
#define DPL_SYSTEM      0
#define DPL_USER        3

#define CPUID_FN8000_0001_ECX_SVM                   (1UL << 2)
#define CPUID_FN0000_0001_ECX_HYPERVISOR_PRESENT    (1UL << 31)
#define CPUID_FN8000_000A_EDX_NP                    (1UL << 0)

#define CPUID_MAX_STANDARD_FN_NUMBER_AND_VENDOR_STRING          0x00000000
#define CPUID_PROCESSOR_AND_PROCESSOR_FEATURE_IDENTIFIERS       0x00000001
#define CPUID_PROCESSOR_AND_PROCESSOR_FEATURE_IDENTIFIERS_EX    0x80000001
#define CPUID_SVM_FEATURES                                      0x8000000a



#define CPUID_HV_VENDOR_AND_MAX_FUNCTIONS   0x40000000
#define CPUID_HV_INTERFACE                  0x40000001




#define CPUID_UNLOAD_SIMPLE_SVM     0x41414141
#define CPUID_PROBE_SIMPLE_SVM      0x4fffffff










#define SV_DEBUG_BREAK() \
    if (KD_DEBUGGER_NOT_PRESENT) \
    { \
        NOTHING; \
    } \
    else \
    { \
        __debugbreak(); \
    } \
    reinterpret_cast<void*>(0)




static PVOID g_PowerCallbackRegistration;






#pragma prefast(push)
#pragma prefast(disable : 26826, "C-style variable arguments needed for DbgPrint.")
_IRQL_requires_max_(DISPATCH_LEVEL)
_IRQL_requires_same_
static
VOID
SvDebugPrint (
    _In_z_ _Printf_format_string_ PCSTR Format,
    ...
    )
{
    va_list argList;

    va_start(argList, Format);
    vDbgPrintExWithPrefix("[SimpleSvm] ",
                          DPFLTR_IHVDRIVER_ID,
                          DPFLTR_ERROR_LEVEL,
                          Format,
                          argList);
    va_end(argList);
}
#pragma prefast(pop)















__drv_allocatesMem(Mem)
_Post_writable_byte_size_(NumberOfBytes)
_Post_maybenull_
_IRQL_requires_max_(DISPATCH_LEVEL)
_IRQL_requires_same_
_Must_inspect_result_
static
PVOID
SvAllocatePageAlingedPhysicalMemory (
    _In_ SIZE_T NumberOfBytes
    )
{
    PVOID memory;

    
    
    
    
    NT_ASSERT(NumberOfBytes >= PAGE_SIZE);

    memory = ExAllocatePool2(POOL_FLAG_NON_PAGED, NumberOfBytes, 'MVSS');
    if (memory != nullptr)
    {
        NT_ASSERT(PAGE_ALIGN(memory) == memory);
        RtlZeroMemory(memory, NumberOfBytes);
    }
    return memory;
}







_IRQL_requires_max_(DISPATCH_LEVEL)
_IRQL_requires_same_
static
VOID
SvFreePageAlingedPhysicalMemory (
    _Pre_notnull_ __drv_freesMem(Mem) PVOID BaseAddress
    )
{
    ExFreePoolWithTag(BaseAddress, 'MVSS');
}














_Post_writable_byte_size_(NumberOfBytes)
_Post_maybenull_
_IRQL_requires_max_(DISPATCH_LEVEL)
_IRQL_requires_same_
_Must_inspect_result_
static
PVOID
SvAllocateContiguousMemory (
    _In_ SIZE_T NumberOfBytes
    )
{
    PVOID memory;
    PHYSICAL_ADDRESS boundary, lowest, highest;

    boundary.QuadPart = lowest.QuadPart = 0;
    highest.QuadPart = -1;

    memory = MmAllocateContiguousNodeMemory(NumberOfBytes,
                                            lowest,
                                            highest,
                                            boundary,
                                            PAGE_READWRITE,
                                            MM_ANY_NODE_OK);
    if (memory != nullptr)
    {
        RtlZeroMemory(memory, NumberOfBytes);
    }
    return memory;
}






_IRQL_requires_max_(DISPATCH_LEVEL)
_IRQL_requires_same_
static
VOID
SvFreeContiguousMemory (
    _In_ PVOID BaseAddress
    )
{
    MmFreeContiguousMemory(BaseAddress);
}



static NTSTATUS SvEnableDirectFlushOnProcessor(
    _Inout_ PSHARED_VIRTUAL_PROCESSOR_DATA SharedVpData)
{
    UINT64 assistMsr = __readmsr(0x40000073);
    UINT64 vpIndex = __readmsr(0x40000002);
    PHYSICAL_ADDRESS assistPa;
    PVOID assistVa;
    volatile LONG* nestedFeatures;
    LONG oldFeatures;

    if (!(assistMsr & 1) || vpIndex >= RTL_NUMBER_OF(SharedVpData->VpAssistMappings))
        return STATUS_NOT_SUPPORTED;
    assistPa.QuadPart = assistMsr & ~0xfffull;
    assistVa = MmMapIoSpaceEx(assistPa, PAGE_SIZE, PAGE_READWRITE | PAGE_NOCACHE);
    if (assistVa == nullptr)
        return STATUS_INSUFFICIENT_RESOURCES;

    nestedFeatures = reinterpret_cast<volatile LONG*>(
        static_cast<PUCHAR>(assistVa) + 0x20);
    oldFeatures = *nestedFeatures;
    SharedVpData->OriginalDirectHypercall[vpIndex] =
        static_cast<UINT8>(oldFeatures & 1);
    SharedVpData->VpAssistMappings[vpIndex] = assistVa;
    InterlockedOr(nestedFeatures, 1);
    return STATUS_SUCCESS;
}

static VOID SvDisableDirectFlushOnProcessor(
    _Inout_ PSHARED_VIRTUAL_PROCESSOR_DATA SharedVpData)
{
    UINT64 vpIndex = __readmsr(0x40000002);
    if (vpIndex < RTL_NUMBER_OF(SharedVpData->VpAssistMappings))
    {
        PVOID assistVa = SharedVpData->VpAssistMappings[vpIndex];
        if (assistVa != nullptr)
        {
            if (!SharedVpData->OriginalDirectHypercall[vpIndex])
            {
                volatile LONG* nestedFeatures = reinterpret_cast<volatile LONG*>(
                    static_cast<PUCHAR>(assistVa) + 0x20);
                InterlockedAnd(nestedFeatures, ~1L);
            }
            SharedVpData->VpAssistMappings[vpIndex] = nullptr;
            MmUnmapIoSpace(assistVa, PAGE_SIZE);
        }
    }
}






_IRQL_requires_same_
static
VOID
SvInjectGeneralProtectionException (
    _Inout_ PVIRTUAL_PROCESSOR_DATA VpData
    )
{
    EVENTINJ event;

    
    
    
    
    
    event.AsUInt64 = 0;
    event.Fields.Vector = 13;
    event.Fields.Type = 3;
    event.Fields.ErrorCodeValid = 1;
    event.Fields.Valid = 1;
    VpData->GuestVmcb.ControlArea.EventInj = event.AsUInt64;
}

static VOID SvInjectInvalidOpcode(PVIRTUAL_PROCESSOR_DATA vpData)
{
    EVENTINJ event = {};
    event.Fields.Vector = 6;
    event.Fields.Type = 3;
    event.Fields.Valid = 1;
    vpData->GuestVmcb.ControlArea.EventInj = event.AsUInt64;
}

static VOID SvInjectBreakpoint(PVIRTUAL_PROCESSOR_DATA vpData)
{
    EVENTINJ event = {};
    event.Fields.Vector = 3;
    event.Fields.Type = 3;
    event.Fields.Valid = 1;
    vpData->GuestVmcb.ControlArea.EventInj = event.AsUInt64;
}

static VOID SvInjectPageFault(PVIRTUAL_PROCESSOR_DATA vpData)
{
    
    
    EVENTINJ event = {};
    event.Fields.Vector = 14;
    event.Fields.Type = 3;
    event.Fields.ErrorCodeValid = 1;
    event.Fields.ErrorCode = static_cast<UINT32>(
        vpData->GuestVmcb.ControlArea.ExitInfo1);
    event.Fields.Valid = 1;
    vpData->GuestVmcb.StateSaveArea.Cr2 =
        vpData->GuestVmcb.ControlArea.ExitInfo2;
    vpData->GuestVmcb.ControlArea.EventInj = event.AsUInt64;
}














_IRQL_requires_same_
static
VOID
SvHandleCpuid (
    _Inout_ PVIRTUAL_PROCESSOR_DATA VpData,
    _Inout_ PGUEST_CONTEXT GuestContext
    )
{
    int registers[4];   
    int leaf, subLeaf;
    SEGMENT_ATTRIBUTE attribute;

    
    
    
    leaf = static_cast<int>(GuestContext->VpRegs->Rax);
    subLeaf = static_cast<int>(GuestContext->VpRegs->Rcx);
    __cpuidex(registers, leaf, subLeaf);

    switch (leaf)
    {
    case 0x4ffffffd:
        if (VpData->GuestVmcb.StateSaveArea.Cpl == DPL_USER &&
            InterlockedCompareExchange(&g_HvLabEnabled, 0, 0) != 0 &&
            g_NptAliasObservedLow == static_cast<LONG>(0x43453032u))
        {
            registers[0] = 0x4ffffffd;
            registers[1] = static_cast<int>(SvAcfHvMask(
                static_cast<UINT32>(subLeaf)));
            registers[2] = 0x41434631; 
            registers[3] = 0;
            InterlockedExchange(&g_AcfLastSeed, subLeaf);
            InterlockedExchange(&g_AcfLastMask, registers[1]);
            InterlockedIncrement(&g_AcfCalls);
        }
        break;
    case 0x4ffffffe:
        
        
        if (subLeaf == 0x43594355 &&
            VpData->GuestVmcb.StateSaveArea.Cpl == DPL_USER &&
            GuestContext->VpRegs->R10 == 0x4856435049443131ULL)
        {
            UINT64 result = SvHvFlowCall(
                VpData->GuestVmcb.StateSaveArea.Cr3, 0x3021,
                GuestContext->VpRegs->R8, GuestContext->VpRegs->R9,
                MAXUINT64);
            registers[0] = static_cast<int>(static_cast<UINT32>(result));
            registers[1] = 0x43594355;
            registers[2] = 0;
            registers[3] = static_cast<int>(static_cast<UINT32>(result >> 32));
        }
        break;
    case CPUID_PROCESSOR_AND_PROCESSOR_FEATURE_IDENTIFIERS:
        
        
        
        
        
        registers[2] |= CPUID_FN0000_0001_ECX_HYPERVISOR_PRESENT;
        break;
    case 0x40000004:
        if (VpData->HostStackLayout.SharedVpData->UseHyperVDirectFlush)
        {
            
            registers[0] |= (1 << 1) | (1 << 2);
        }
        break;
    case CPUID_PROBE_SIMPLE_SVM:
        
        registers[0] = CPUID_PROBE_SIMPLE_SVM;
        if (subLeaf == 1)
        {
            UINT64 vmId = VpData->HostStackLayout.SharedVpData->VmId;
            registers[1] = static_cast<UINT32>(vmId);
            registers[2] = static_cast<UINT32>(vmId >> 32);
            registers[3] = 0x00020000; 
        }
        else if (subLeaf == 2)
        {
            registers[1] = g_HvTrapAfterFlush;
            registers[2] = 0;
            registers[3] = 0;
        }
        else if (subLeaf == 3)
        {
            registers[1] = g_NptReadHits;
            registers[2] = g_NptWriteHits;
            registers[3] = static_cast<int>(
                static_cast<UINT32>(g_NptLastWrite));
        }
        else if (subLeaf == 4)
        {
            auto shared = VpData->HostStackLayout.SharedVpData;
            registers[1] = g_NptAliasObservedLow;
            registers[2] = *reinterpret_cast<volatile UINT32*>(shared->AliasPage);
            registers[3] = 0x414c4953; 
        }
        else if (subLeaf == 5)
        {
            registers[1] = g_HvLabCalls;
            registers[2] = g_HvLabRejects;
            registers[3] = 0x484d5554; 
        }
        else if (subLeaf == 6)
        {
            registers[1] = g_HvFlowDirectSteps;
            registers[2] = g_HvFlowUdSteps;
            registers[3] = g_HvFlowBpSteps;
        }
        else if (subLeaf == 7)
        {
            registers[1] = g_AcfLastSeed;
            registers[2] = g_AcfLastMask;
            registers[3] = g_AcfCalls;
        }
        else if (subLeaf == 8)
        {
            registers[1] = g_HvAddressGatePfHits;
            registers[2] = g_HvAddressGateUdHits;
            registers[3] = 0x41444754; 
        }
        else
        {
            registers[1] = 'pmiS';  
            registers[2] = 'vSel';
            registers[3] = '   m';
        }
        break;
    case CPUID_UNLOAD_SIMPLE_SVM:
        if (subLeaf == CPUID_UNLOAD_SIMPLE_SVM)
        {
            
            
            
            attribute.AsUInt16 = VpData->GuestVmcb.StateSaveArea.SsAttrib;
            if (attribute.Fields.Dpl == DPL_SYSTEM)
            {
                GuestContext->ExitVm = TRUE;
            }
        }
        break;
    default:
        break;
    }

    
    
    
    
    
    
    GuestContext->VpRegs->Rax = static_cast<UINT32>(registers[0]);
    GuestContext->VpRegs->Rbx = static_cast<UINT32>(registers[1]);
    GuestContext->VpRegs->Rcx = static_cast<UINT32>(registers[2]);
    GuestContext->VpRegs->Rdx = static_cast<UINT32>(registers[3]);

    
    
    
    
    
    
    
    
    
    
    
    

    
    
    
    VpData->GuestVmcb.StateSaveArea.Rip = VpData->GuestVmcb.ControlArea.NRip;
}












_IRQL_requires_same_
static
VOID
SvHandleMsrAccess (
    _Inout_ PVIRTUAL_PROCESSOR_DATA VpData,
    _Inout_ PGUEST_CONTEXT GuestContext
    )
{
    ULARGE_INTEGER value;
    UINT32 msr;
    BOOLEAN writeAccess;

    msr = GuestContext->VpRegs->Rcx & MAXUINT32;
    writeAccess = (VpData->GuestVmcb.ControlArea.ExitInfo1 != 0);

    
    
    
    
    if (msr == IA32_MSR_EFER)
    {
        
        
        
        NT_ASSERT(writeAccess != FALSE);

        value.LowPart = GuestContext->VpRegs->Rax & MAXUINT32;
        value.HighPart = GuestContext->VpRegs->Rdx & MAXUINT32;
        if ((value.QuadPart & EFER_SVME) == 0)
        {
            
            
            
            
            
            SvInjectGeneralProtectionException(VpData);
            return;
        }

        
        
        
        
        
        
        
        
        
        
        VpData->GuestVmcb.StateSaveArea.Efer = value.QuadPart;
    }
    else
    {
        
        
        
        
        
        
        
        
        
        
        
        
        NT_ASSERT(((msr > 0x00001fff) && (msr < 0xc0000000)) ||
                  ((msr > 0xc0001fff) && (msr < 0xc0010000)) ||
                   (msr > 0xc0011fff));

        
        
        
        
        
        
        
        
        
        
        
        
        if (writeAccess != FALSE)
        {
            value.LowPart = GuestContext->VpRegs->Rax & MAXUINT32;
            value.HighPart = GuestContext->VpRegs->Rdx & MAXUINT32;
            __writemsr(msr, value.QuadPart);
        }
        else
        {
            value.QuadPart = __readmsr(msr);
            GuestContext->VpRegs->Rax = value.LowPart;
            GuestContext->VpRegs->Rdx = value.HighPart;
        }
    }

    
    
    
    VpData->GuestVmcb.StateSaveArea.Rip = VpData->GuestVmcb.ControlArea.NRip;
}









_IRQL_requires_same_
static
VOID
SvHandleVmrun (
    _Inout_ PVIRTUAL_PROCESSOR_DATA VpData,
    _Inout_ PGUEST_CONTEXT GuestContext
    )
{
    UNREFERENCED_PARAMETER(GuestContext);

    SvInjectGeneralProtectionException(VpData);
}





















_IRQL_requires_same_
EXTERN_C
BOOLEAN
NTAPI
SvHandleVmExit (
    _Inout_ PVIRTUAL_PROCESSOR_DATA VpData,
    _Inout_ PGUEST_REGISTERS GuestRegisters,
    _Inout_ PUCHAR XmmState
    )
{
    GUEST_CONTEXT guestContext;
    KIRQL oldIrql;

    guestContext.VpRegs = GuestRegisters;
    guestContext.ExitVm = FALSE;

    
    
    
    __svm_vmload(VpData->HostStackLayout.HostVmcbPa);

    NT_ASSERT(VpData->HostStackLayout.Reserved1 == MAXUINT64);

    
    
    
    
    
    
    
    
    
    
    oldIrql = KeGetCurrentIrql();
    if (oldIrql < DISPATCH_LEVEL)
    {
        KeRaiseIrqlToDpcLevel();
    }

    
    
    
    
    GuestRegisters->Rax = VpData->GuestVmcb.StateSaveArea.Rax;

    
    
    VpData->GuestVmcb.ControlArea.TlbControl = 0;

    
    
    
    
    
    VpData->HostStackLayout.TrapFrame.Rsp = VpData->GuestVmcb.StateSaveArea.Rsp;
    VpData->HostStackLayout.TrapFrame.Rip = VpData->GuestVmcb.ControlArea.NRip;

    
    
    
    switch (VpData->GuestVmcb.ControlArea.ExitCode)
    {
    case VMEXIT_CPUID:
        SvHandleCpuid(VpData, &guestContext);
        break;
    case VMEXIT_MSR:
        SvHandleMsrAccess(VpData, &guestContext);
        break;
    case VMEXIT_EXCEPTION_UD:
        if (VpData->GuestVmcb.StateSaveArea.Cpl == DPL_USER)
        {
            UINT64 target = 0;
            if (SvHvAddressGateLookup(VpData->GuestVmcb.StateSaveArea.Cr3,
                                      VpData->GuestVmcb.StateSaveArea.Rip,
                                      2, &target))
            {
                VpData->GuestVmcb.StateSaveArea.Rip = target;
                InterlockedIncrement(&g_HvAddressGateUdHits);
                break;
            }
        }
        
        
        if (VpData->GuestVmcb.StateSaveArea.Cpl == DPL_USER &&
            GuestRegisters->R10 == 0x4856545241503131ULL &&
            GuestRegisters->Rdx == 0x3011)
        {
            UINT64 result = SvHvFlowCall(
                VpData->GuestVmcb.StateSaveArea.Cr3, 0x3011,
                GuestRegisters->R8, GuestRegisters->R9,
                VpData->GuestVmcb.StateSaveArea.Rip);
            if (result != MAXUINT64)
            {
                GuestRegisters->Rax = result;
                VpData->GuestVmcb.StateSaveArea.Rip += 2; 
                break;
            }
        }
        SvInjectInvalidOpcode(VpData);
        break;
    case VMEXIT_EXCEPTION_BP:
        
        
        if (VpData->GuestVmcb.StateSaveArea.Cpl == DPL_USER &&
            GuestRegisters->R10 == 0x4856425245414b31ULL &&
            GuestRegisters->Rdx == 0x3041)
        {
            UINT64 result = SvHvFlowCall(
                VpData->GuestVmcb.StateSaveArea.Cr3, 0x3041,
                GuestRegisters->R8, GuestRegisters->R9,
                VpData->GuestVmcb.StateSaveArea.Rip);
            if (result != MAXUINT64)
            {
                GuestRegisters->Rax = result;
                VpData->GuestVmcb.StateSaveArea.Rip =
                    VpData->GuestVmcb.ControlArea.NRip;
                break;
            }
        }
        VpData->GuestVmcb.StateSaveArea.Rip =
            VpData->GuestVmcb.ControlArea.NRip;
        SvInjectBreakpoint(VpData);
        break;
    case VMEXIT_EXCEPTION_PF:
        if (VpData->GuestVmcb.StateSaveArea.Cpl == DPL_USER &&
            (VpData->GuestVmcb.ControlArea.ExitInfo1 & 2) == 0 &&
            VpData->GuestVmcb.StateSaveArea.Rip !=
                VpData->GuestVmcb.ControlArea.ExitInfo2)
        {
            UINT64 target = 0;
            if (SvHvAddressGateLookup(VpData->GuestVmcb.StateSaveArea.Cr3,
                                      VpData->GuestVmcb.StateSaveArea.Rip,
                                      3, &target,
                                      VpData->GuestVmcb.ControlArea.ExitInfo2))
            {
                
                
                GuestRegisters->R10 = target;
                break;
            }
        }
        if (VpData->GuestVmcb.StateSaveArea.Cpl == DPL_USER &&
            (VpData->GuestVmcb.ControlArea.ExitInfo1 & 2) == 0 &&
            VpData->GuestVmcb.StateSaveArea.Rip ==
                VpData->GuestVmcb.ControlArea.ExitInfo2)
        {
            UINT64 target = 0;
            if (SvHvAddressGateLookup(VpData->GuestVmcb.StateSaveArea.Cr3,
                                      VpData->GuestVmcb.StateSaveArea.Rip,
                                      1, &target))
            {
                VpData->GuestVmcb.StateSaveArea.Rip = target;
                InterlockedIncrement(&g_HvAddressGatePfHits);
                break;
            }
        }
        SvInjectPageFault(VpData);
        break;
    case VMEXIT_NPF:
        if ((VpData->GuestVmcb.ControlArea.ExitInfo2 & ~0xfffULL) ==
            VpData->HostStackLayout.SharedVpData->GuardGpa)
        {
            UINT64 rip = VpData->GuestVmcb.StateSaveArea.Rip;
            UINT64 error = VpData->GuestVmcb.ControlArea.ExitInfo1;
            if (VpData->GuestVmcb.StateSaveArea.Cpl == DPL_SYSTEM &&
                GuestRegisters->Rcx == reinterpret_cast<UINT64>(g_NptProbePage))
            {
                if (rip == reinterpret_cast<UINT64>(SvNptReadProbe) &&
                    (error & 2) == 0)
                {
                    GuestRegisters->Rax = 0x43594355504e5054ULL;
                    InterlockedIncrement(&g_NptReadHits);
                    VpData->GuestVmcb.StateSaveArea.Rip += 3;
                    break;
                }
                if (rip == reinterpret_cast<UINT64>(SvNptWriteProbe) &&
                    (error & 2) != 0)
                {
                    InterlockedExchange64(&g_NptLastWrite,
                                          static_cast<LONG64>(GuestRegisters->Rdx));
                    InterlockedIncrement(&g_NptWriteHits);
                    VpData->GuestVmcb.StateSaveArea.Rip += 3;
                    break;
                }
            }
            SvInjectGeneralProtectionException(VpData);
            break;
        }
        
        
        SV_DEBUG_BREAK();
        KeBugCheck(MANUALLY_INITIATED_CRASH);
        break;
    case VMEXIT_VMRUN:
        SvHandleVmrun(VpData, &guestContext);
        break;
    case VMEXIT_VMMCALL:
        if (VpData->GuestVmcb.StateSaveArea.Cpl == DPL_USER)
        {
            UINT32 armSite = SvHvArmRunSite(
                VpData->GuestVmcb.StateSaveArea.Cr3,
                VpData->GuestVmcb.StateSaveArea.Rip,
                GuestRegisters, VpData);
            if (armSite == 1)
            {
                VpData->GuestVmcb.StateSaveArea.Rip =
                    VpData->GuestVmcb.ControlArea.NRip;
                break;
            }
            if (armSite == 2)
            {
                SvInjectInvalidOpcode(VpData);
                break;
            }
        }
        
        
        if (GuestRegisters->Rcx == 0x43434248564c4142ULL)
        {
            InterlockedIncrement(&g_HvLabCalls);
            UINT64 armStatus = 1;
            if (VpData->GuestVmcb.StateSaveArea.Cpl != DPL_USER)
            {
                GuestRegisters->Rax = MAXUINT64;
            }
            else
            {
                UINT64 cr3 = VpData->GuestVmcb.StateSaveArea.Cr3;
                UINT64 site = GuestRegisters->Rdx;
                if (site >= 0x3100 && site <= 0x31ff)
                {
                    GuestRegisters->Rax = SvHvArmCall(
                        cr3, site, GuestRegisters->R8, GuestRegisters->R10,
                        GuestRegisters->R9, GuestRegisters->Rax, &armStatus);
                    if (GuestRegisters->Rax != MAXUINT64 && armStatus == 1)
                        armStatus = 0;
                    GuestRegisters->Rdx = armStatus;
                }
                else if (site == 0x3200)
                {
                    GuestRegisters->Rax = SvHvArmInlineWord(
                        GuestRegisters->R8, GuestRegisters->R9,
                        GuestRegisters->R10, GuestRegisters->Rax,
                        GuestRegisters->Rbx, &armStatus);
                    GuestRegisters->Rdx = armStatus;
                }
                else if (site >= 0x3201 && site <= 0x3203)
                {
                    bool bound = SvHvArmQuickBind(
                        cr3, VpData->GuestVmcb.ControlArea.NRip,
                        site, GuestRegisters->R8, GuestRegisters->R9,
                        GuestRegisters->R10);
                    GuestRegisters->Rax = bound ? 0 : MAXUINT64;
                    GuestRegisters->Rdx = bound ? 0 : 1;
                    armStatus = bound ? 0 : 1;
                }
                else if (site == 0x3301)
                {
                    bool bound = SvHvAddressGateBind(
                        cr3, GuestRegisters->R8, GuestRegisters->R9,
                        GuestRegisters->R10,
                        static_cast<UINT32>(GuestRegisters->Rax));
                    GuestRegisters->Rax = bound ? 0 : MAXUINT64;
                    GuestRegisters->Rdx = bound ? 0 : 1;
                    armStatus = bound ? 0 : 1;
                }
                else if (site == 0x3302)
                {
                    bool bound = SvHvAddressGateBind(
                        cr3, GuestRegisters->R8, GuestRegisters->R10,
                        GuestRegisters->Rax, 3, GuestRegisters->R9);
                    GuestRegisters->Rax = bound ? 0 : MAXUINT64;
                    GuestRegisters->Rdx = bound ? 0 : 1;
                    armStatus = bound ? 0 : 1;
                }
                else if (site >= 0x3050 && site <= 0x305f)
                    GuestRegisters->Rax = SvHvCheckCall(
                        cr3, site, GuestRegisters->R8, GuestRegisters->R9);
                else if (site >= 0x3000 && site <= 0x30ff)
                    GuestRegisters->Rax = SvHvFlowCall(
                        cr3, site, GuestRegisters->R8, GuestRegisters->R9, 0);
                else
                    GuestRegisters->Rax = SvHvLabCall(
                        cr3, site, GuestRegisters->R8, GuestRegisters->R9);
            }
            if ((GuestRegisters->Rax == MAXUINT64 && armStatus != 0) ||
                armStatus > 1)
                InterlockedIncrement(&g_HvLabRejects);
            VpData->GuestVmcb.StateSaveArea.Rip =
                VpData->GuestVmcb.ControlArea.NRip;
            break;
        }
        if (!VpData->HostStackLayout.SharedVpData->UseHyperVDirectFlush)
        {
            
            
            SvInjectInvalidOpcode(VpData);
            break;
        }
        
        
        {
            UINT16 callCode = static_cast<UINT16>(GuestRegisters->Rcx);
            SvForwardVmmcall(GuestRegisters, XmmState);
            
            
            
            if ((GuestRegisters->Rax & 0xffff) == 0 &&
                (callCode == 0x0002 || callCode == 0x0003 ||
                 callCode == 0x0013 || callCode == 0x0014))
            {
                VpData->GuestVmcb.ControlArea.TlbControl = 1;
            }
        }
        VpData->GuestVmcb.StateSaveArea.Rip = VpData->GuestVmcb.ControlArea.NRip;
        break;
    case 0xf0000000ULL: 
        if (VpData->GuestVmcb.ControlArea.ExitInfo1 != 1)
        {
            KeBugCheck(MANUALLY_INITIATED_CRASH);
        }
        InterlockedIncrement(&g_HvTrapAfterFlush);
        
        
        
        if (VpData->GuestVmcb.ControlArea.NRip >
            VpData->GuestVmcb.StateSaveArea.Rip &&
            VpData->GuestVmcb.ControlArea.NRip <=
            VpData->GuestVmcb.StateSaveArea.Rip + 3)
        {
            VpData->GuestVmcb.StateSaveArea.Rip =
                VpData->GuestVmcb.ControlArea.NRip;
        }
        break;
    default:
        SV_DEBUG_BREAK();
#pragma prefast(suppress : __WARNING_USE_OTHER_FUNCTION, "Unrecoverable path.")
        KeBugCheck(MANUALLY_INITIATED_CRASH);
    }

    
    
    
    
    
    if (oldIrql < DISPATCH_LEVEL)
    {
        KeLowerIrql(oldIrql);
    }

    
    
    
    if (guestContext.ExitVm != FALSE)
    {
        NT_ASSERT(VpData->GuestVmcb.ControlArea.ExitCode == VMEXIT_CPUID);

        
        
        
        
        
        
        guestContext.VpRegs->Rax = reinterpret_cast<UINT64>(VpData) & MAXUINT32;
        guestContext.VpRegs->Rbx = VpData->GuestVmcb.ControlArea.NRip;
        guestContext.VpRegs->Rcx = VpData->GuestVmcb.StateSaveArea.Rsp;
        guestContext.VpRegs->Rdx = reinterpret_cast<UINT64>(VpData) >> 32;

        
        
        
        __svm_vmload(MmGetPhysicalAddress(&VpData->GuestVmcb).QuadPart);

        
        
        
        
        
        
        _disable();
        __svm_stgi();

        
        
        
        
        __writemsr(IA32_MSR_EFER, __readmsr(IA32_MSR_EFER) & ~EFER_SVME);
        __writeeflags(VpData->GuestVmcb.StateSaveArea.Rflags);
        goto Exit;
    }

    
    
    
    
    VpData->GuestVmcb.StateSaveArea.Rax = guestContext.VpRegs->Rax;

Exit:
    NT_ASSERT(VpData->HostStackLayout.Reserved1 == MAXUINT64);
    return guestContext.ExitVm;
}























_IRQL_requires_same_
_Check_return_
static
UINT16
SvGetSegmentAccessRight (
    _In_ UINT16 SegmentSelector,
    _In_ ULONG_PTR GdtBase
    )
{
    PSEGMENT_DESCRIPTOR descriptor;
    SEGMENT_ATTRIBUTE attribute;

    
    
    
    descriptor = reinterpret_cast<PSEGMENT_DESCRIPTOR>(
                                        GdtBase + (SegmentSelector & ~RPL_MASK));

    
    
    
    
    
    attribute.Fields.Type = descriptor->Fields.Type;
    attribute.Fields.System = descriptor->Fields.System;
    attribute.Fields.Dpl = descriptor->Fields.Dpl;
    attribute.Fields.Present = descriptor->Fields.Present;
    attribute.Fields.Avl = descriptor->Fields.Avl;
    attribute.Fields.LongMode = descriptor->Fields.LongMode;
    attribute.Fields.DefaultBit = descriptor->Fields.DefaultBit;
    attribute.Fields.Granularity = descriptor->Fields.Granularity;
    attribute.Fields.Reserved1 = 0;

    return attribute.AsUInt16;
}









_IRQL_requires_max_(DISPATCH_LEVEL)
_IRQL_requires_min_(PASSIVE_LEVEL)
_IRQL_requires_same_
_Check_return_
static
BOOLEAN
SvIsSimpleSvmHypervisorInstalled (
    VOID
    )
{
    int registers[4];   
    char vendorId[13];

    
    
    
    __cpuid(registers, CPUID_PROBE_SIMPLE_SVM);
    RtlCopyMemory(vendorId + 0, &registers[1], sizeof(registers[1]));
    RtlCopyMemory(vendorId + 4, &registers[2], sizeof(registers[2]));
    RtlCopyMemory(vendorId + 8, &registers[3], sizeof(registers[3]));
    vendorId[12] = ANSI_NULL;

    return (strcmp(vendorId, "SimpleSvm   ") == 0);
}













_IRQL_requires_max_(DISPATCH_LEVEL)
_IRQL_requires_min_(PASSIVE_LEVEL)
_IRQL_requires_same_
static
VOID
SvPrepareForVirtualization (
    _Inout_ PVIRTUAL_PROCESSOR_DATA VpData,
    _In_ PSHARED_VIRTUAL_PROCESSOR_DATA SharedVpData,
    _In_ const CONTEXT* ContextRecord
    )
{
    DESCRIPTOR_TABLE_REGISTER gdtr, idtr;
    PHYSICAL_ADDRESS guestVmcbPa, hostVmcbPa, hostStateAreaPa, pml4BasePa, msrpmPa;

    
    
    
    
    _sgdt(&gdtr);
    __sidt(&idtr);

    guestVmcbPa = MmGetPhysicalAddress(&VpData->GuestVmcb);
    hostVmcbPa = MmGetPhysicalAddress(&VpData->HostVmcb);
    hostStateAreaPa = MmGetPhysicalAddress(&VpData->HostStateArea);
    pml4BasePa = MmGetPhysicalAddress(&SharedVpData->Pml4Entries);
    msrpmPa = MmGetPhysicalAddress(SharedVpData->MsrPermissionsMap);

    
    
    
    
    
    
    
    
    
    
    VpData->GuestVmcb.ControlArea.InterceptMisc1 |= SVM_INTERCEPT_MISC1_CPUID;
    VpData->GuestVmcb.ControlArea.InterceptException |= (1UL << 6); 
    VpData->GuestVmcb.ControlArea.InterceptException |= (1UL << 3); 
    VpData->GuestVmcb.ControlArea.InterceptException |= (1UL << 14); 
    VpData->GuestVmcb.ControlArea.InterceptMisc2 |= SVM_INTERCEPT_MISC2_VMRUN;
    VpData->GuestVmcb.ControlArea.InterceptMisc2 |= SVM_INTERCEPT_MISC2_VMMCALL;

    
    
    
    
    VpData->GuestVmcb.ControlArea.InterceptMisc1 |= SVM_INTERCEPT_MISC1_MSR_PROT;
    VpData->GuestVmcb.ControlArea.MsrpmBasePa = msrpmPa.QuadPart;

    
    
    
    
    
    
    
    
    VpData->GuestVmcb.ControlArea.GuestAsid = 1;

    
    
    
    
    
    
    
    
    
    
    
    
    VpData->GuestVmcb.ControlArea.NpEnable |= SVM_NP_ENABLE_NP_ENABLE;
    VpData->GuestVmcb.ControlArea.NCr3 = pml4BasePa.QuadPart;

    if (SharedVpData->UseHyperVDirectFlush)
    {
        
        
        VpData->GuestVmcb.ControlArea.HyperV.EnlightenmentsControl = 1;
        VpData->GuestVmcb.ControlArea.HyperV.VpId =
            static_cast<UINT32>(__readmsr(0x40000002));
        VpData->GuestVmcb.ControlArea.HyperV.VmId = SharedVpData->VmId;
        VpData->GuestVmcb.ControlArea.HyperV.PartitionAssistPage =
            MmGetPhysicalAddress(SharedVpData->PartitionAssistPage).QuadPart;
        VpData->GuestVmcb.ControlArea.VmcbClean &= ~(1ULL << 31);
    }

    
    
    
    
    
    VpData->GuestVmcb.StateSaveArea.GdtrBase = gdtr.Base;
    VpData->GuestVmcb.StateSaveArea.GdtrLimit = gdtr.Limit;
    VpData->GuestVmcb.StateSaveArea.IdtrBase = idtr.Base;
    VpData->GuestVmcb.StateSaveArea.IdtrLimit = idtr.Limit;

    VpData->GuestVmcb.StateSaveArea.CsLimit = GetSegmentLimit(ContextRecord->SegCs);
    VpData->GuestVmcb.StateSaveArea.DsLimit = GetSegmentLimit(ContextRecord->SegDs);
    VpData->GuestVmcb.StateSaveArea.EsLimit = GetSegmentLimit(ContextRecord->SegEs);
    VpData->GuestVmcb.StateSaveArea.SsLimit = GetSegmentLimit(ContextRecord->SegSs);
    VpData->GuestVmcb.StateSaveArea.CsSelector = ContextRecord->SegCs;
    VpData->GuestVmcb.StateSaveArea.DsSelector = ContextRecord->SegDs;
    VpData->GuestVmcb.StateSaveArea.EsSelector = ContextRecord->SegEs;
    VpData->GuestVmcb.StateSaveArea.SsSelector = ContextRecord->SegSs;
    VpData->GuestVmcb.StateSaveArea.CsAttrib = SvGetSegmentAccessRight(ContextRecord->SegCs, gdtr.Base);
    VpData->GuestVmcb.StateSaveArea.DsAttrib = SvGetSegmentAccessRight(ContextRecord->SegDs, gdtr.Base);
    VpData->GuestVmcb.StateSaveArea.EsAttrib = SvGetSegmentAccessRight(ContextRecord->SegEs, gdtr.Base);
    VpData->GuestVmcb.StateSaveArea.SsAttrib = SvGetSegmentAccessRight(ContextRecord->SegSs, gdtr.Base);

    VpData->GuestVmcb.StateSaveArea.Efer = __readmsr(IA32_MSR_EFER);
    VpData->GuestVmcb.StateSaveArea.Cr0 = __readcr0();
    VpData->GuestVmcb.StateSaveArea.Cr2 = __readcr2();
    VpData->GuestVmcb.StateSaveArea.Cr3 = __readcr3();
    VpData->GuestVmcb.StateSaveArea.Cr4 = __readcr4();
    VpData->GuestVmcb.StateSaveArea.Rflags = ContextRecord->EFlags;
    VpData->GuestVmcb.StateSaveArea.Rsp = ContextRecord->Rsp;
    VpData->GuestVmcb.StateSaveArea.Rip = ContextRecord->Rip;
    VpData->GuestVmcb.StateSaveArea.GPat = __readmsr(IA32_MSR_PAT);

    
    
    
    
    
    
    
    
    
    
    
    
    
    __svm_vmsave(guestVmcbPa.QuadPart);

    
    
    
    VpData->HostStackLayout.Reserved1 = MAXUINT64;
    VpData->HostStackLayout.SharedVpData = SharedVpData;
    VpData->HostStackLayout.Self = VpData;
    VpData->HostStackLayout.HostVmcbPa = hostVmcbPa.QuadPart;
    VpData->HostStackLayout.GuestVmcbPa = guestVmcbPa.QuadPart;

    
    
    
    
    
    __writemsr(SVM_MSR_VM_HSAVE_PA, hostStateAreaPa.QuadPart);

    
    
    
    
    __svm_vmsave(hostVmcbPa.QuadPart);
}












_IRQL_requires_max_(DISPATCH_LEVEL)
_IRQL_requires_min_(PASSIVE_LEVEL)
_IRQL_requires_same_
_Check_return_
static
NTSTATUS
SvVirtualizeProcessor (
    _In_opt_ PVOID Context
    )
{
    NTSTATUS status;
    PSHARED_VIRTUAL_PROCESSOR_DATA sharedVpData;
    PVIRTUAL_PROCESSOR_DATA vpData;
    PCONTEXT contextRecord;

    SV_DEBUG_BREAK();

    vpData = nullptr;
    sharedVpData = nullptr;

    NT_ASSERT(ARGUMENT_PRESENT(Context));
    _Analysis_assume_(ARGUMENT_PRESENT(Context));

    contextRecord = static_cast<PCONTEXT>(ExAllocatePool2(
                                                        POOL_FLAG_NON_PAGED,
                                                        sizeof(*contextRecord),
                                                        'MVSS'));
    if (contextRecord == nullptr)
    {
        SvDebugPrint("Insufficient memory.\n");
        status = STATUS_INSUFFICIENT_RESOURCES;
        goto Exit;
    }

    
    
    
#pragma prefast(suppress : __WARNING_MEMORY_LEAK, "Ownership is taken on success.")
    vpData = static_cast<PVIRTUAL_PROCESSOR_DATA>(
            SvAllocatePageAlingedPhysicalMemory(sizeof(VIRTUAL_PROCESSOR_DATA)));
    if (vpData == nullptr)
    {
        SvDebugPrint("Insufficient memory.\n");
        status = STATUS_INSUFFICIENT_RESOURCES;
        goto Exit;
    }

    
    
    
    
    
    
    RtlCaptureContext(contextRecord);

    
    
    
    
    
    
    
    
    if (SvIsSimpleSvmHypervisorInstalled() == FALSE)
    {
        SvDebugPrint("Attempting to virtualize the processor.\n");
        sharedVpData = static_cast<PSHARED_VIRTUAL_PROCESSOR_DATA>(Context);

        if (sharedVpData->UseHyperVDirectFlush)
        {
            status = SvEnableDirectFlushOnProcessor(sharedVpData);
            if (!NT_SUCCESS(status))
            {
                SvDebugPrint("Could not enable Hyper-V nested direct flush.\n");
                goto Exit;
            }
        }

        
        
        
        
        __writemsr(IA32_MSR_EFER, __readmsr(IA32_MSR_EFER) | EFER_SVME);

        
        
        
        
        SvPrepareForVirtualization(vpData, sharedVpData, contextRecord);

        
        
        
        
        
        
        
        SvLaunchVm(&vpData->HostStackLayout.GuestVmcbPa);
        SV_DEBUG_BREAK();
#pragma prefast(suppress : __WARNING_USE_OTHER_FUNCTION, "Unrecoverble path.")
        KeBugCheck(MANUALLY_INITIATED_CRASH);
    }

    SvDebugPrint("The processor has been virtualized.\n");
    status = STATUS_SUCCESS;

Exit:
    if (contextRecord != nullptr)
    {
        ExFreePoolWithTag(contextRecord, 'MVSS');
    }
    if ((!NT_SUCCESS(status)) && (vpData != nullptr))
    {
        if (sharedVpData != nullptr)
        {
            if (sharedVpData->UseHyperVDirectFlush)
                SvDisableDirectFlushOnProcessor(sharedVpData);
        }
        
        
        
        
        SvFreePageAlingedPhysicalMemory(vpData);
    }
    return status;
}





















_IRQL_requires_max_(APC_LEVEL)
_IRQL_requires_min_(PASSIVE_LEVEL)
_IRQL_requires_same_
_Check_return_
static
NTSTATUS
SvExecuteOnEachProcessor (
    _In_ NTSTATUS (*Callback)(PVOID),
    _In_opt_ PVOID Context,
    _Out_opt_ PULONG NumOfProcessorCompleted
    )
{
    NTSTATUS status;
    ULONG i, numOfProcessors;
    PROCESSOR_NUMBER processorNumber;
    GROUP_AFFINITY affinity, oldAffinity;

    status = STATUS_SUCCESS;

    
    
    
    numOfProcessors = KeQueryActiveProcessorCountEx(ALL_PROCESSOR_GROUPS);

    for (i = 0; i < numOfProcessors; i++)
    {
        
        
        
        status = KeGetProcessorNumberFromIndex(i, &processorNumber);
        if (!NT_SUCCESS(status))
        {
            goto Exit;
        }

        
        
        
        affinity.Group = processorNumber.Group;
        affinity.Mask = 1ULL << processorNumber.Number;
        affinity.Reserved[0] = affinity.Reserved[1] = affinity.Reserved[2] = 0;
        KeSetSystemGroupAffinityThread(&affinity, &oldAffinity);

        
        
        
        status = Callback(Context);

        
        
        
        KeRevertToUserGroupAffinityThread(&oldAffinity);

        
        
        
        if (!NT_SUCCESS(status))
        {
            goto Exit;
        }
    }

Exit:
    
    
    
    
    NT_ASSERT(!NT_SUCCESS(status) || (i == numOfProcessors));

    
    
    
    
    if (ARGUMENT_PRESENT(NumOfProcessorCompleted))
    {
        *NumOfProcessorCompleted = i;
    }
    return status;
}













_IRQL_requires_max_(DISPATCH_LEVEL)
_IRQL_requires_min_(PASSIVE_LEVEL)
_IRQL_requires_same_
_Check_return_
static
NTSTATUS
SvDevirtualizeProcessor (
    _In_opt_ PVOID Context
    )
{
    int registers[4];   
    UINT64 high, low;
    PVIRTUAL_PROCESSOR_DATA vpData;
    PSHARED_VIRTUAL_PROCESSOR_DATA* sharedVpDataPtr;

    if (!ARGUMENT_PRESENT(Context))
    {
        goto Exit;
    }

    
    
    
    
    
    __cpuidex(registers, CPUID_UNLOAD_SIMPLE_SVM, CPUID_UNLOAD_SIMPLE_SVM);
    if (registers[2] != 'SSVM')
    {
        goto Exit;
    }

    SvDebugPrint("The processor has been de-virtualized.\n");

    
    
    
    high = registers[3];
    low = registers[0] & MAXUINT32;
    vpData = reinterpret_cast<PVIRTUAL_PROCESSOR_DATA>(high << 32 | low);
    NT_ASSERT(vpData->HostStackLayout.Reserved1 == MAXUINT64);

    
    
    
    sharedVpDataPtr = static_cast<PSHARED_VIRTUAL_PROCESSOR_DATA*>(Context);
    *sharedVpDataPtr = vpData->HostStackLayout.SharedVpData;
    if ((*sharedVpDataPtr)->UseHyperVDirectFlush)
        SvDisableDirectFlushOnProcessor(*sharedVpDataPtr);
    SvFreePageAlingedPhysicalMemory(vpData);

Exit:
    return STATUS_SUCCESS;
}








_IRQL_requires_max_(APC_LEVEL)
_IRQL_requires_min_(PASSIVE_LEVEL)
_IRQL_requires_same_
static
VOID
SvDevirtualizeAllProcessors (
    VOID
    )
{
    PSHARED_VIRTUAL_PROCESSOR_DATA sharedVpData;

    sharedVpData = nullptr;

    
    
    
    NT_VERIFY(NT_SUCCESS(SvExecuteOnEachProcessor(SvDevirtualizeProcessor,
                                                  &sharedVpData,
                                                  nullptr)));
    if (sharedVpData != nullptr)
    {
        if (g_HvFlowKey != nullptr)
            RtlSecureZeroMemory(g_HvFlowKey, sizeof(UINT64) * 2);
        g_HvFlowKey = nullptr;
        SvFreeContiguousMemory(sharedVpData->MsrPermissionsMap);
        if (sharedVpData->PartitionAssistPage != nullptr)
            SvFreeContiguousMemory(sharedVpData->PartitionAssistPage);
        SvFreePageAlingedPhysicalMemory(sharedVpData);
    }
    g_NptProbePage = nullptr;
}























_IRQL_requires_same_
static
VOID
SvBuildMsrPermissionsMap (
    _Inout_ PVOID MsrPermissionsMap
    )
{
    constexpr UINT32 BITS_PER_MSR = 2;
    constexpr UINT32 SECOND_MSR_RANGE_BASE = 0xc0000000;
    constexpr UINT32 SECOND_MSRPM_OFFSET = 0x800 * CHAR_BIT;
    RTL_BITMAP bitmapHeader;
    ULONG offsetFrom2ndBase, offset;

    
    
    
    RtlInitializeBitMap(&bitmapHeader,
                        static_cast<PULONG>(MsrPermissionsMap),
                        SVM_MSR_PERMISSIONS_MAP_SIZE * CHAR_BIT
                        );
    RtlClearAllBits(&bitmapHeader);

    
    
    
    
    
    offsetFrom2ndBase = (IA32_MSR_EFER - SECOND_MSR_RANGE_BASE) * BITS_PER_MSR;
    offset = SECOND_MSRPM_OFFSET + offsetFrom2ndBase;

    
    
    
    RtlSetBits(&bitmapHeader, offset + 1, 1);
}






















_IRQL_requires_same_
static
VOID
SvBuildNestedPageTables (
    _Out_ PSHARED_VIRTUAL_PROCESSOR_DATA SharedVpData
    )
{
    ULONG64 pdptBasePa, pdBasePa, translationPa;

    
    
    
    
    
    for (ULONG64 pml4Index = 0; pml4Index < 2; pml4Index++) {
        PPML4_ENTRY_2MB pml4e = &SharedVpData->Pml4Entries[pml4Index];
        PPML4E_TREE pml4eTree = &SharedVpData->Pml4eTrees[pml4Index];

        
        
        
        
        
        
        
        
        
        
        
        
        pdptBasePa = MmGetPhysicalAddress(&pml4eTree->PdptEntries).QuadPart;
        pml4e->Fields.PageFrameNumber = pdptBasePa >> PAGE_SHIFT;
        pml4e->Fields.Valid = 1;
        pml4e->Fields.Write = 1;
        pml4e->Fields.User = 1;

        
        
        
        for (ULONG64 pdptIndex = 0; pdptIndex < 512; pdptIndex++)
        {
            
            
            
            pdBasePa = MmGetPhysicalAddress(&pml4eTree->PdEntries[pdptIndex][0]).QuadPart;
            pml4eTree->PdptEntries[pdptIndex].Fields.PageFrameNumber = pdBasePa >> PAGE_SHIFT;
            pml4eTree->PdptEntries[pdptIndex].Fields.Valid = 1;
            pml4eTree->PdptEntries[pdptIndex].Fields.Write = 1;
            pml4eTree->PdptEntries[pdptIndex].Fields.User = 1;

            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            for (ULONG64 pdIndex = 0; pdIndex < 512; pdIndex++)
            {
                
                
                
                
                
                
                translationPa = (pml4Index * 512 * 512) + (pdptIndex * 512) + pdIndex;
                pml4eTree->PdEntries[pdptIndex][pdIndex].Fields.PageFrameNumber = translationPa;
                pml4eTree->PdEntries[pdptIndex][pdIndex].Fields.Valid = 1;
                pml4eTree->PdEntries[pdptIndex][pdIndex].Fields.Write = 1;
                pml4eTree->PdEntries[pdptIndex][pdIndex].Fields.User = 1;
                pml4eTree->PdEntries[pdptIndex][pdIndex].Fields.LargePage = 1;
            }
        }
    }

    
    
    UINT64 splitGpas[2] = { SharedVpData->GuardGpa,
                            SharedVpData->AliasGpa };
    for (UINT64 splitIndex = 0; splitIndex < 2; ++splitIndex)
    {
        UINT64 gpa = splitGpas[splitIndex];
        UINT64 splitBase = gpa & ~0x1fffffULL;
        if (splitIndex == 1 &&
            splitBase == (SharedVpData->GuardGpa & ~0x1fffffULL))
            continue;
        for (UINT64 i = 0; i < 512; ++i)
        {
            PML4_ENTRY_2MB* pte = &SharedVpData->NptSplitEntries[splitIndex][i];
            pte->AsUInt64 = 0;
            pte->Fields.PageFrameNumber = (splitBase >> PAGE_SHIFT) + i;
            pte->Fields.Valid = 1;
            pte->Fields.Write = 1;
            pte->Fields.User = 1;
        }
        PD_ENTRY_2MB* splitPde = &SharedVpData->Pml4eTrees[gpa >> 39]
            .PdEntries[(gpa >> 30) & 511][(gpa >> 21) & 511];
        splitPde->AsUInt64 =
            (MmGetPhysicalAddress(SharedVpData->NptSplitEntries[splitIndex])
                 .QuadPart & ~0xfffULL) | 7ULL;
    }
    SharedVpData->NptSplitEntries[0]
        [(SharedVpData->GuardGpa >> PAGE_SHIFT) & 511].AsUInt64 = 0;
    UINT64 aliasSplit = (SharedVpData->AliasGpa & ~0x1fffffULL) ==
        (SharedVpData->GuardGpa & ~0x1fffffULL) ? 0 : 1;
    SharedVpData->NptSplitEntries[aliasSplit]
        [(SharedVpData->AliasGpa >> PAGE_SHIFT) & 511].Fields.PageFrameNumber =
            SharedVpData->SourceGpa >> PAGE_SHIFT;
}









_IRQL_requires_same_
_Check_return_
static
BOOLEAN
SvIsSvmSupported (
    VOID
    )
{
    BOOLEAN svmSupported;
    int registers[4];   
    ULONG64 vmcr;

    svmSupported = FALSE;

    
    
    
    
    
    __cpuid(registers, CPUID_MAX_STANDARD_FN_NUMBER_AND_VENDOR_STRING);
    if ((registers[1] != 'htuA') ||
        (registers[3] != 'itne') ||
        (registers[2] != 'DMAc'))
    {
        goto Exit;
    }

    
    
    
    
    __cpuid(registers, CPUID_PROCESSOR_AND_PROCESSOR_FEATURE_IDENTIFIERS_EX);
    if ((registers[2] & CPUID_FN8000_0001_ECX_SVM) == 0)
    {
        goto Exit;
    }

    
    
    
    
    
    __cpuid(registers, CPUID_SVM_FEATURES);
    if ((registers[3] & CPUID_FN8000_000A_EDX_NP) == 0)
    {
        goto Exit;
    }

    
    
    
    
    
    
    vmcr = __readmsr(SVM_MSR_VM_CR);
    if ((vmcr & SVM_VM_CR_SVMDIS) != 0)
    {
        goto Exit;
    }

    svmSupported = TRUE;

Exit:
    return svmSupported;
}












_IRQL_requires_max_(APC_LEVEL)
_IRQL_requires_min_(PASSIVE_LEVEL)
_IRQL_requires_same_
_Check_return_
static
NTSTATUS
SvVirtualizeAllProcessors (
    VOID
    )
{
    NTSTATUS status;
    PSHARED_VIRTUAL_PROCESSOR_DATA sharedVpData;
    ULONG numOfProcessorsCompleted;
    int hvRegs[4];
    BOOLEAN useHyperVDirectFlush;

    sharedVpData = nullptr;
    numOfProcessorsCompleted = 0;
    useHyperVDirectFlush = FALSE;

    
    
    
    
    if (SvIsSvmSupported() == FALSE)
    {
        SvDebugPrint("SVM is not fully supported on this processor.\n");
        status = STATUS_HV_FEATURE_UNAVAILABLE;
        goto Exit;
    }

    
    
    if (KeQueryActiveGroupCount() != 1 ||
        KeQueryActiveProcessorCountEx(ALL_PROCESSOR_GROUPS) > 64)
    {
        status = STATUS_NOT_SUPPORTED;
        goto Exit;
    }
    __cpuid(hvRegs, CPUID_PROCESSOR_AND_PROCESSOR_FEATURE_IDENTIFIERS);
    if (!(hvRegs[2] & CPUID_FN0000_0001_ECX_HYPERVISOR_PRESENT))
    {
        status = STATUS_HV_FEATURE_UNAVAILABLE;
        goto Exit;
    }
    __cpuid(hvRegs, CPUID_HV_VENDOR_AND_MAX_FUNCTIONS);
    if (RtlCompareMemory(&hvRegs[1], "Microsoft Hv", 12) == 12)
    {
        if (static_cast<UINT32>(hvRegs[0]) < 0x4000000a)
        {
            status = STATUS_HV_FEATURE_UNAVAILABLE;
            goto Exit;
        }
        __cpuid(hvRegs, CPUID_HV_INTERFACE);
        if (static_cast<UINT32>(hvRegs[0]) != 0x31237648)
        {
            status = STATUS_HV_FEATURE_UNAVAILABLE;
            goto Exit;
        }
        __cpuid(hvRegs, 0x4000000a);
        if (!(static_cast<UINT32>(hvRegs[0]) & (1u << 17)))
        {
            status = STATUS_HV_FEATURE_UNAVAILABLE;
            goto Exit;
        }
        useHyperVDirectFlush = TRUE;
    }
    else if (RtlCompareMemory(&hvRegs[1], "VMwareVMware", 12) != 12)
    {
        status = STATUS_HV_FEATURE_UNAVAILABLE;
        goto Exit;
    }

    
    
    
    
#pragma prefast(suppress : __WARNING_MEMORY_LEAK, "Ownership is taken on success.")
    sharedVpData = static_cast<PSHARED_VIRTUAL_PROCESSOR_DATA>(
        SvAllocatePageAlingedPhysicalMemory(sizeof(SHARED_VIRTUAL_PROCESSOR_DATA)));
    if (sharedVpData == nullptr)
    {
        SvDebugPrint("Insufficient memory.\n");
        status = STATUS_INSUFFICIENT_RESOURCES;
        goto Exit;
    }

    sharedVpData->UseHyperVDirectFlush = useHyperVDirectFlush;
    
    
    sharedVpData->VmId = __rdtsc() | 1ULL;
    sharedVpData->GuardGpa =
        MmGetPhysicalAddress(sharedVpData->GuardPage).QuadPart;
    sharedVpData->AliasGpa =
        MmGetPhysicalAddress(sharedVpData->AliasPage).QuadPart;
    sharedVpData->SourceGpa =
        MmGetPhysicalAddress(sharedVpData->SourcePage).QuadPart;
    if (sharedVpData->GuardGpa >= (1ULL << 40) ||
        sharedVpData->AliasGpa >= (1ULL << 40) ||
        sharedVpData->SourceGpa >= (1ULL << 40) ||
        sharedVpData->GuardGpa == sharedVpData->AliasGpa ||
        sharedVpData->GuardGpa == sharedVpData->SourceGpa ||
        sharedVpData->AliasGpa == sharedVpData->SourceGpa)
    {
        status = STATUS_NOT_SUPPORTED;
        goto Exit;
    }
    status = BCryptGenRandom(nullptr, sharedVpData->GuardPage,
                             sizeof(UINT64) * 2,
                             BCRYPT_USE_SYSTEM_PREFERRED_RNG);
    if (!NT_SUCCESS(status))
        goto Exit;
    g_HvFlowKey = reinterpret_cast<UINT64*>(sharedVpData->GuardPage);
    g_HvFlowSequence = static_cast<LONG64>(g_HvFlowKey[0] | 1ULL);
    g_NptProbePage = sharedVpData->GuardPage;
    *reinterpret_cast<UINT64*>(sharedVpData->AliasPage) =
        0x414c49534241434bULL;
    *reinterpret_cast<UINT64*>(sharedVpData->SourcePage) =
        0x534f555243453031ULL;

    
    
    
    sharedVpData->MsrPermissionsMap = SvAllocateContiguousMemory(
                                                    SVM_MSR_PERMISSIONS_MAP_SIZE);
    if (sharedVpData->MsrPermissionsMap == nullptr)
    {
        SvDebugPrint("Insufficient memory.\n");
        status = STATUS_INSUFFICIENT_RESOURCES;
        goto Exit;
    }

    if (useHyperVDirectFlush)
    {
        sharedVpData->PartitionAssistPage = SvAllocateContiguousMemory(PAGE_SIZE);
        if (sharedVpData->PartitionAssistPage == nullptr)
        {
            status = STATUS_INSUFFICIENT_RESOURCES;
            goto Exit;
        }
    }

    
    
    
    SvBuildNestedPageTables(sharedVpData);
    SvBuildMsrPermissionsMap(sharedVpData->MsrPermissionsMap);

    
    
    
    
    
    
    
    
    
    
    
    
    status = SvExecuteOnEachProcessor(SvVirtualizeProcessor,
                                      sharedVpData,
                                      &numOfProcessorsCompleted);

Exit:
    if (!NT_SUCCESS(status))
    {
        
        
        
        if (numOfProcessorsCompleted != 0)
        {
            
            
            
            
            NT_ASSERT(sharedVpData != nullptr);
            SvDevirtualizeAllProcessors();
        }
        else
        {
            
            
            
            
            if (sharedVpData != nullptr)
            {
                if (g_HvFlowKey != nullptr)
                    RtlSecureZeroMemory(g_HvFlowKey, sizeof(UINT64) * 2);
                g_HvFlowKey = nullptr;
                if (sharedVpData->MsrPermissionsMap != nullptr)
                {
                    SvFreeContiguousMemory(sharedVpData->MsrPermissionsMap);
                }
                if (sharedVpData->PartitionAssistPage != nullptr)
                {
                    SvFreeContiguousMemory(sharedVpData->PartitionAssistPage);
                }
                SvFreePageAlingedPhysicalMemory(sharedVpData);
            }
        }
        g_NptProbePage = nullptr;
    }
    return status;
}









_Use_decl_annotations_
EXTERN_C
NTSTATUS
DriverEntry (
    PDRIVER_OBJECT DriverObject,
    PUNICODE_STRING RegistryPath
    )
{
    NTSTATUS status;
    UNICODE_STRING objectName;
    OBJECT_ATTRIBUTES objectAttributes;
    PCALLBACK_OBJECT callbackObject;
    PVOID callbackRegistration;
    bool processNotifyRegistered;

    UNREFERENCED_PARAMETER(RegistryPath);

    SV_DEBUG_BREAK();

    callbackRegistration = nullptr;
    processNotifyRegistered = false;
    g_HvLabNextToken = static_cast<LONG64>(__rdtsc() | 1);
    DriverObject->DriverUnload = SvDriverUnload;

    
    
    
    
    
    
    
    
    ExInitializeDriverRuntime(DrvRtPoolNxOptIn);

    
    
    
    
    
    
    
    
    
    
    
    objectName = RTL_CONSTANT_STRING(L"\\Callback\\PowerState");
    objectAttributes = RTL_CONSTANT_OBJECT_ATTRIBUTES(&objectName,
                                                      OBJ_CASE_INSENSITIVE);
    status = ExCreateCallback(&callbackObject, &objectAttributes, FALSE, TRUE);
    if (!NT_SUCCESS(status))
    {
        SvDebugPrint("Failed to open the power state callback object.\n");
        goto Exit;
    }

    
    
    
    
    callbackRegistration = ExRegisterCallback(callbackObject,
                                              SvPowerCallbackRoutine,
                                              nullptr);
    ObDereferenceObject(callbackObject);
    if (callbackRegistration == nullptr)
    {
        SvDebugPrint("Failed to register a power state callback.\n");
        status = STATUS_UNSUCCESSFUL;
        goto Exit;
    }

    status = PsSetCreateProcessNotifyRoutine(SvProcessNotify, FALSE);
    if (!NT_SUCCESS(status))
    {
        SvDebugPrint("Failed to register process exit notification.\n");
        goto Exit;
    }
    processNotifyRegistered = true;

    
    
    
    status = SvVirtualizeAllProcessors();
    if (NT_SUCCESS(status))
    {
        UINT64 observed = SvNptReadProbe(g_NptProbePage);
        SvNptWriteProbe(g_NptProbePage, 0x2077abcd51474e50ULL);
        
        
        auto shared = reinterpret_cast<PSHARED_VIRTUAL_PROCESSOR_DATA>(
            reinterpret_cast<UINT8*>(g_NptProbePage) -
            FIELD_OFFSET(SHARED_VIRTUAL_PROCESSOR_DATA, GuardPage));
        volatile UINT64* alias = reinterpret_cast<volatile UINT64*>(
            shared->AliasPage);
        volatile UINT64* source = reinterpret_cast<volatile UINT64*>(
            shared->SourcePage);
        BOOLEAN aliasOk = (*alias == 0x534f555243453031ULL &&
                           *source == 0x534f555243453031ULL);
        *alias = 0x534f555243453032ULL;
        aliasOk = aliasOk && *source == 0x534f555243453032ULL &&
                  *alias == 0x534f555243453032ULL;
        if (aliasOk)
            InterlockedExchange(&g_NptAliasObservedLow,
                                static_cast<LONG>(*alias));
        if (observed != 0x43594355504e5054ULL ||
            g_NptReadHits != 1 || g_NptWriteHits != 1 ||
            g_NptLastWrite != static_cast<LONG64>(0x2077abcd51474e50ULL) ||
            !aliasOk)
        {
            SvDevirtualizeAllProcessors();
            status = STATUS_DATA_ERROR;
        }
    }

Exit:
    if (NT_SUCCESS(status))
    {
        
        
        
        NT_ASSERT(callbackRegistration);
        g_PowerCallbackRegistration = callbackRegistration;
        InterlockedExchange(&g_HvLabEnabled, 1);
    }
    else
    {
        
        
        
        if (processNotifyRegistered)
            PsSetCreateProcessNotifyRoutine(SvProcessNotify, TRUE);
        if (callbackRegistration != nullptr)
        {
            ExUnregisterCallback(callbackRegistration);
        }
    }
    return status;
}








_Use_decl_annotations_
static
VOID
SvDriverUnload (
    PDRIVER_OBJECT DriverObject
    )
{
    UNREFERENCED_PARAMETER(DriverObject);

    SV_DEBUG_BREAK();

    
    InterlockedExchange(&g_HvLabEnabled, 0);

    NTSTATUS notifyStatus = PsSetCreateProcessNotifyRoutine(
        SvProcessNotify, TRUE);
    if (!NT_SUCCESS(notifyStatus))
        SvDebugPrint("Failed to unregister process exit notification.\n");

    
    
    NT_ASSERT(g_PowerCallbackRegistration);
    ExUnregisterCallback(g_PowerCallbackRegistration);

    
    
    
    SvDevirtualizeAllProcessors();
    RtlSecureZeroMemory(g_HvFlowSessions, sizeof(g_HvFlowSessions));
    RtlSecureZeroMemory(g_HvCheckSessions, sizeof(g_HvCheckSessions));
    RtlSecureZeroMemory(g_HvArmSessions, sizeof(g_HvArmSessions));
}


















_Use_decl_annotations_
static
VOID
SvPowerCallbackRoutine (
    PVOID CallbackContext,
    PVOID Argument1,
    PVOID Argument2
    )
{
    UNREFERENCED_PARAMETER(CallbackContext);

    
    
    
    
    if (Argument1 != reinterpret_cast<PVOID>(PO_CB_SYSTEM_STATE_LOCK))
    {
        goto Exit;
    }

    if (Argument2 != FALSE)
    {
        
        
        
        if (NT_SUCCESS(SvVirtualizeAllProcessors()))
            InterlockedExchange(&g_HvLabEnabled, 1);
        else
            SvDebugPrint("Failed to re-virtualize after power transition.\n");
    }
    else
    {
        InterlockedExchange(&g_HvLabEnabled, 0);
        
        
        
        
        SvDevirtualizeAllProcessors();
        RtlZeroMemory(g_HvLabSessions, sizeof(g_HvLabSessions));
        RtlSecureZeroMemory(g_HvFlowSessions, sizeof(g_HvFlowSessions));
        RtlSecureZeroMemory(g_HvCheckSessions, sizeof(g_HvCheckSessions));
        RtlSecureZeroMemory(g_HvArmSessions, sizeof(g_HvArmSessions));
    }

Exit:
    return;
}
