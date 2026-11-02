








#pragma once

#include <basetsd.h>




#define SVM_MSR_PERMISSIONS_MAP_SIZE    (PAGE_SIZE * 2)




#define SVM_MSR_VM_CR                   0xc0010114
#define SVM_MSR_VM_HSAVE_PA             0xc0010117

#define SVM_VM_CR_SVMDIS                (1UL << 4)




#define SVM_INTERCEPT_MISC1_CPUID       (1UL << 18)
#define SVM_INTERCEPT_MISC1_MSR_PROT    (1UL << 28)
#define SVM_INTERCEPT_MISC2_VMRUN       (1UL << 0)
#define SVM_INTERCEPT_MISC2_VMMCALL     (1UL << 1)
#define SVM_NP_ENABLE_NP_ENABLE         (1UL << 0)

typedef struct _VMCB_CONTROL_AREA
{
    UINT16 InterceptCrRead;             
    UINT16 InterceptCrWrite;            
    UINT16 InterceptDrRead;             
    UINT16 InterceptDrWrite;            
    UINT32 InterceptException;          
    UINT32 InterceptMisc1;              
    UINT32 InterceptMisc2;              
    UINT8 Reserved1[0x03c - 0x014];     
    UINT16 PauseFilterThreshold;        
    UINT16 PauseFilterCount;            
    UINT64 IopmBasePa;                  
    UINT64 MsrpmBasePa;                 
    UINT64 TscOffset;                   
    UINT32 GuestAsid;                   
    UINT32 TlbControl;                  
    UINT64 VIntr;                       
    UINT64 InterruptShadow;             
    UINT64 ExitCode;                    
    UINT64 ExitInfo1;                   
    UINT64 ExitInfo2;                   
    UINT64 ExitIntInfo;                 
    UINT64 NpEnable;                    
    UINT64 AvicApicBar;                 
    UINT64 GuestPaOfGhcb;               
    UINT64 EventInj;                    
    UINT64 NCr3;                        
    UINT64 LbrVirtualizationEnable;     
    UINT64 VmcbClean;                   
    UINT64 NRip;                        
    UINT8 NumOfBytesFetched;            
    UINT8 GuestInstructionBytes[15];    
    UINT64 AvicApicBackingPagePointer;  
    UINT64 Reserved2;                   
    UINT64 AvicLogicalTablePointer;     
    UINT64 AvicPhysicalTablePointer;    
    UINT64 Reserved3;                   
    UINT64 VmcbSaveStatePointer;        
    UINT8 Reserved4[0x3e0 - 0x110];     
    struct
    {
        UINT32 EnlightenmentsControl;   
        UINT32 VpId;                    
        UINT64 VmId;                    
        UINT64 PartitionAssistPage;     
        UINT64 Reserved;                
    } HyperV;                           
} VMCB_CONTROL_AREA, *PVMCB_CONTROL_AREA;
static_assert(sizeof(VMCB_CONTROL_AREA) == 0x400,
              "VMCB_CONTROL_AREA Size Mismatch");




typedef struct _VMCB_STATE_SAVE_AREA
{
    UINT16 EsSelector;                  
    UINT16 EsAttrib;                    
    UINT32 EsLimit;                     
    UINT64 EsBase;                      
    UINT16 CsSelector;                  
    UINT16 CsAttrib;                    
    UINT32 CsLimit;                     
    UINT64 CsBase;                      
    UINT16 SsSelector;                  
    UINT16 SsAttrib;                    
    UINT32 SsLimit;                     
    UINT64 SsBase;                      
    UINT16 DsSelector;                  
    UINT16 DsAttrib;                    
    UINT32 DsLimit;                     
    UINT64 DsBase;                      
    UINT16 FsSelector;                  
    UINT16 FsAttrib;                    
    UINT32 FsLimit;                     
    UINT64 FsBase;                      
    UINT16 GsSelector;                  
    UINT16 GsAttrib;                    
    UINT32 GsLimit;                     
    UINT64 GsBase;                      
    UINT16 GdtrSelector;                
    UINT16 GdtrAttrib;                  
    UINT32 GdtrLimit;                   
    UINT64 GdtrBase;                    
    UINT16 LdtrSelector;                
    UINT16 LdtrAttrib;                  
    UINT32 LdtrLimit;                   
    UINT64 LdtrBase;                    
    UINT16 IdtrSelector;                
    UINT16 IdtrAttrib;                  
    UINT32 IdtrLimit;                   
    UINT64 IdtrBase;                    
    UINT16 TrSelector;                  
    UINT16 TrAttrib;                    
    UINT32 TrLimit;                     
    UINT64 TrBase;                      
    UINT8 Reserved1[0x0cb - 0x0a0];     
    UINT8 Cpl;                          
    UINT32 Reserved2;                   
    UINT64 Efer;                        
    UINT8 Reserved3[0x148 - 0x0d8];     
    UINT64 Cr4;                         
    UINT64 Cr3;                         
    UINT64 Cr0;                         
    UINT64 Dr7;                         
    UINT64 Dr6;                         
    UINT64 Rflags;                      
    UINT64 Rip;                         
    UINT8 Reserved4[0x1d8 - 0x180];     
    UINT64 Rsp;                         
    UINT8 Reserved5[0x1f8 - 0x1e0];     
    UINT64 Rax;                         
    UINT64 Star;                        
    UINT64 LStar;                       
    UINT64 CStar;                       
    UINT64 SfMask;                      
    UINT64 KernelGsBase;                
    UINT64 SysenterCs;                  
    UINT64 SysenterEsp;                 
    UINT64 SysenterEip;                 
    UINT64 Cr2;                         
    UINT8 Reserved6[0x268 - 0x248];     
    UINT64 GPat;                        
    UINT64 DbgCtl;                      
    UINT64 BrFrom;                      
    UINT64 BrTo;                        
    UINT64 LastExcepFrom;               
    UINT64 LastExcepTo;                 
} VMCB_STATE_SAVE_AREA, *PVMCB_STATE_SAVE_AREA;
static_assert(sizeof(VMCB_STATE_SAVE_AREA) == 0x298,
              "VMCB_STATE_SAVE_AREA Size Mismatch");




typedef struct _VMCB
{
    VMCB_CONTROL_AREA ControlArea;
    VMCB_STATE_SAVE_AREA StateSaveArea;
    UINT8 Reserved1[0x1000 - sizeof(VMCB_CONTROL_AREA) - sizeof(VMCB_STATE_SAVE_AREA)];
} VMCB, *PVMCB;
static_assert(sizeof(VMCB) == 0x1000,
              "VMCB Size Mismatch");




typedef struct _EVENTINJ
{
    union
    {
        UINT64 AsUInt64;
        struct
        {
            UINT64 Vector : 8;          
            UINT64 Type : 3;            
            UINT64 ErrorCodeValid : 1;  
            UINT64 Reserved1 : 19;      
            UINT64 Valid : 1;           
            UINT64 ErrorCode : 32;      
        } Fields;
    };
} EVENTINJ, *PEVENTINJ;
static_assert(sizeof(EVENTINJ) == 8,
              "EVENTINJ Size Mismatch");




#define VMEXIT_CR0_READ             0x0000
#define VMEXIT_CR1_READ             0x0001
#define VMEXIT_CR2_READ             0x0002
#define VMEXIT_CR3_READ             0x0003
#define VMEXIT_CR4_READ             0x0004
#define VMEXIT_CR5_READ             0x0005
#define VMEXIT_CR6_READ             0x0006
#define VMEXIT_CR7_READ             0x0007
#define VMEXIT_CR8_READ             0x0008
#define VMEXIT_CR9_READ             0x0009
#define VMEXIT_CR10_READ            0x000a
#define VMEXIT_CR11_READ            0x000b
#define VMEXIT_CR12_READ            0x000c
#define VMEXIT_CR13_READ            0x000d
#define VMEXIT_CR14_READ            0x000e
#define VMEXIT_CR15_READ            0x000f
#define VMEXIT_CR0_WRITE            0x0010
#define VMEXIT_CR1_WRITE            0x0011
#define VMEXIT_CR2_WRITE            0x0012
#define VMEXIT_CR3_WRITE            0x0013
#define VMEXIT_CR4_WRITE            0x0014
#define VMEXIT_CR5_WRITE            0x0015
#define VMEXIT_CR6_WRITE            0x0016
#define VMEXIT_CR7_WRITE            0x0017
#define VMEXIT_CR8_WRITE            0x0018
#define VMEXIT_CR9_WRITE            0x0019
#define VMEXIT_CR10_WRITE           0x001a
#define VMEXIT_CR11_WRITE           0x001b
#define VMEXIT_CR12_WRITE           0x001c
#define VMEXIT_CR13_WRITE           0x001d
#define VMEXIT_CR14_WRITE           0x001e
#define VMEXIT_CR15_WRITE           0x001f
#define VMEXIT_DR0_READ             0x0020
#define VMEXIT_DR1_READ             0x0021
#define VMEXIT_DR2_READ             0x0022
#define VMEXIT_DR3_READ             0x0023
#define VMEXIT_DR4_READ             0x0024
#define VMEXIT_DR5_READ             0x0025
#define VMEXIT_DR6_READ             0x0026
#define VMEXIT_DR7_READ             0x0027
#define VMEXIT_DR8_READ             0x0028
#define VMEXIT_DR9_READ             0x0029
#define VMEXIT_DR10_READ            0x002a
#define VMEXIT_DR11_READ            0x002b
#define VMEXIT_DR12_READ            0x002c
#define VMEXIT_DR13_READ            0x002d
#define VMEXIT_DR14_READ            0x002e
#define VMEXIT_DR15_READ            0x002f
#define VMEXIT_DR0_WRITE            0x0030
#define VMEXIT_DR1_WRITE            0x0031
#define VMEXIT_DR2_WRITE            0x0032
#define VMEXIT_DR3_WRITE            0x0033
#define VMEXIT_DR4_WRITE            0x0034
#define VMEXIT_DR5_WRITE            0x0035
#define VMEXIT_DR6_WRITE            0x0036
#define VMEXIT_DR7_WRITE            0x0037
#define VMEXIT_DR8_WRITE            0x0038
#define VMEXIT_DR9_WRITE            0x0039
#define VMEXIT_DR10_WRITE           0x003a
#define VMEXIT_DR11_WRITE           0x003b
#define VMEXIT_DR12_WRITE           0x003c
#define VMEXIT_DR13_WRITE           0x003d
#define VMEXIT_DR14_WRITE           0x003e
#define VMEXIT_DR15_WRITE           0x003f
#define VMEXIT_EXCEPTION_DE         0x0040
#define VMEXIT_EXCEPTION_DB         0x0041
#define VMEXIT_EXCEPTION_NMI        0x0042
#define VMEXIT_EXCEPTION_BP         0x0043
#define VMEXIT_EXCEPTION_OF         0x0044
#define VMEXIT_EXCEPTION_BR         0x0045
#define VMEXIT_EXCEPTION_UD         0x0046
#define VMEXIT_EXCEPTION_NM         0x0047
#define VMEXIT_EXCEPTION_DF         0x0048
#define VMEXIT_EXCEPTION_09         0x0049
#define VMEXIT_EXCEPTION_TS         0x004a
#define VMEXIT_EXCEPTION_NP         0x004b
#define VMEXIT_EXCEPTION_SS         0x004c
#define VMEXIT_EXCEPTION_GP         0x004d
#define VMEXIT_EXCEPTION_PF         0x004e
#define VMEXIT_EXCEPTION_15         0x004f
#define VMEXIT_EXCEPTION_MF         0x0050
#define VMEXIT_EXCEPTION_AC         0x0051
#define VMEXIT_EXCEPTION_MC         0x0052
#define VMEXIT_EXCEPTION_XF         0x0053
#define VMEXIT_EXCEPTION_20         0x0054
#define VMEXIT_EXCEPTION_21         0x0055
#define VMEXIT_EXCEPTION_22         0x0056
#define VMEXIT_EXCEPTION_23         0x0057
#define VMEXIT_EXCEPTION_24         0x0058
#define VMEXIT_EXCEPTION_25         0x0059
#define VMEXIT_EXCEPTION_26         0x005a
#define VMEXIT_EXCEPTION_27         0x005b
#define VMEXIT_EXCEPTION_28         0x005c
#define VMEXIT_EXCEPTION_VC         0x005d
#define VMEXIT_EXCEPTION_SX         0x005e
#define VMEXIT_EXCEPTION_31         0x005f
#define VMEXIT_INTR                 0x0060
#define VMEXIT_NMI                  0x0061
#define VMEXIT_SMI                  0x0062
#define VMEXIT_INIT                 0x0063
#define VMEXIT_VINTR                0x0064
#define VMEXIT_CR0_SEL_WRITE        0x0065
#define VMEXIT_IDTR_READ            0x0066
#define VMEXIT_GDTR_READ            0x0067
#define VMEXIT_LDTR_READ            0x0068
#define VMEXIT_TR_READ              0x0069
#define VMEXIT_IDTR_WRITE           0x006a
#define VMEXIT_GDTR_WRITE           0x006b
#define VMEXIT_LDTR_WRITE           0x006c
#define VMEXIT_TR_WRITE             0x006d
#define VMEXIT_RDTSC                0x006e
#define VMEXIT_RDPMC                0x006f
#define VMEXIT_PUSHF                0x0070
#define VMEXIT_POPF                 0x0071
#define VMEXIT_CPUID                0x0072
#define VMEXIT_RSM                  0x0073
#define VMEXIT_IRET                 0x0074
#define VMEXIT_SWINT                0x0075
#define VMEXIT_INVD                 0x0076
#define VMEXIT_PAUSE                0x0077
#define VMEXIT_HLT                  0x0078
#define VMEXIT_INVLPG               0x0079
#define VMEXIT_INVLPGA              0x007a
#define VMEXIT_IOIO                 0x007b
#define VMEXIT_MSR                  0x007c
#define VMEXIT_TASK_SWITCH          0x007d
#define VMEXIT_FERR_FREEZE          0x007e
#define VMEXIT_SHUTDOWN             0x007f
#define VMEXIT_VMRUN                0x0080
#define VMEXIT_VMMCALL              0x0081
#define VMEXIT_VMLOAD               0x0082
#define VMEXIT_VMSAVE               0x0083
#define VMEXIT_STGI                 0x0084
#define VMEXIT_CLGI                 0x0085
#define VMEXIT_SKINIT               0x0086
#define VMEXIT_RDTSCP               0x0087
#define VMEXIT_ICEBP                0x0088
#define VMEXIT_WBINVD               0x0089
#define VMEXIT_MONITOR              0x008a
#define VMEXIT_MWAIT                0x008b
#define VMEXIT_MWAIT_CONDITIONAL    0x008c
#define VMEXIT_XSETBV               0x008d
#define VMEXIT_EFER_WRITE_TRAP      0x008f
#define VMEXIT_CR0_WRITE_TRAP       0x0090
#define VMEXIT_CR1_WRITE_TRAP       0x0091
#define VMEXIT_CR2_WRITE_TRAP       0x0092
#define VMEXIT_CR3_WRITE_TRAP       0x0093
#define VMEXIT_CR4_WRITE_TRAP       0x0094
#define VMEXIT_CR5_WRITE_TRAP       0x0095
#define VMEXIT_CR6_WRITE_TRAP       0x0096
#define VMEXIT_CR7_WRITE_TRAP       0x0097
#define VMEXIT_CR8_WRITE_TRAP       0x0098
#define VMEXIT_CR9_WRITE_TRAP       0x0099
#define VMEXIT_CR10_WRITE_TRAP      0x009a
#define VMEXIT_CR11_WRITE_TRAP      0x009b
#define VMEXIT_CR12_WRITE_TRAP      0x009c
#define VMEXIT_CR13_WRITE_TRAP      0x009d
#define VMEXIT_CR14_WRITE_TRAP      0x009e
#define VMEXIT_CR15_WRITE_TRAP      0x009f
#define VMEXIT_NPF                  0x0400
#define AVIC_INCOMPLETE_IPI         0x0401
#define AVIC_NOACCEL                0x0402
#define VMEXIT_VMGEXIT              0x0403
#define VMEXIT_INVALID              -1
