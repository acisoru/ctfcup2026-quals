#pragma warning(disable: 4996)   /* deprecated pool APIs, kept for Win10 RTM */

#include <ntddk.h>
#include <wdmsec.h>
#include <intrin.h>

#define TARTAROS_KERNEL 1
#include "tartaros_api.h"

#define TARTAROS_POOL_TAG       0x9A3C5E71UL
#define TARTAROS_CTX_MAGIC      0x54584321  /* '!CXT'     */
#define TARTAROS_BUGCHECK_CODE  0xDEADC0DE

#ifndef TARTAROS_DEBUG
#define TARTAROS_DEBUG 0
#endif

#if TARTAROS_DEBUG
#define TAR_LOG(fmt, ...) DbgPrint("[TARTAROS] " fmt "\n", __VA_ARGS__)
#else
#define TAR_LOG(...) ((void)0)
#endif

typedef enum _TARTAROS_STATE {
    TarStateIdle = TARTAROS_ST_IDLE,
    TarStateArmed = TARTAROS_ST_ARMED,
    TarStatePrimed = TARTAROS_ST_PRIMED,
    TarStateRetyped = TARTAROS_ST_RETYPED
} TARTAROS_STATE;

typedef struct _TARTAROS_HANDLE_CTX {
    ULONG   Magic;
    ULONG   State;
    ULONG   ShotsLeft;
    ULONG   Violations;
    ULONG   CommitCount;
    ULONG   Pad;
    ULONG   ViewKey;
    ULONG   StateKey;
    ULONG   ViewArmed;
    TARTAROS_TASK *Task;
} TARTAROS_HANDLE_CTX, *PTARTAROS_HANDLE_CTX;

typedef NTSTATUS (*PTAR_HANDLER)(
    _In_ PDEVICE_OBJECT DeviceObject,
    _In_ PIRP Irp,
    _In_ PIO_STACK_LOCATION IrpSp,
    _Inout_ PTARTAROS_HANDLE_CTX Ctx);

typedef struct _TARTAROS_DISPATCH_ENTRY {
    ULONG         Hash;
    PTAR_HANDLER  Handler;
} TARTAROS_DISPATCH_ENTRY, *PTARTAROS_DISPATCH_ENTRY;

typedef union _TAR_HANDLER_BITS {
    PTAR_HANDLER Handler;
    ULONG_PTR    Bits;
} TAR_HANDLER_BITS;

#ifndef TARTAROS_PAGED_TASK
#define TARTAROS_PAGED_TASK 1
#endif

#ifndef TARTAROS_TASK_ALLOC_MODE
#define TARTAROS_TASK_ALLOC_MODE 1   /* 1 = paged lookaside (validated WNF chain) */
#endif

#if TARTAROS_TASK_ALLOC_MODE == 2

static PAGED_LOOKASIDE_LIST g_TaskLookaside;   /* address only, for the cookie */
#define TAR_TASK_ALLOC()  ExAllocatePoolWithTag(PagedPool, TARTAROS_TASK_SIZE, g_PoolTag)
#define TAR_TASK_FREE(p)  ExFreePoolWithTag((p), g_PoolTag)
#define TAR_TASK_INIT()   STATUS_SUCCESS
#define TAR_TASK_DELETE() ((void)0)

#elif TARTAROS_PAGED_TASK
static PAGED_LOOKASIDE_LIST g_TaskLookaside;
#define TAR_TASK_ALLOC()  ExAllocateFromPagedLookasideList(&g_TaskLookaside)
#define TAR_TASK_FREE(p)  ExFreeToPagedLookasideList(&g_TaskLookaside, (p))
#define TAR_TASK_INIT()   ExInitializePagedLookasideList(&g_TaskLookaside, NULL, NULL, POOL_NX_ALLOCATION, sizeof(TARTAROS_TASK), g_PoolTag, 0)
#define TAR_TASK_DELETE() ExDeletePagedLookasideList(&g_TaskLookaside)
#else
static NPAGED_LOOKASIDE_LIST g_TaskLookaside;
#define TAR_TASK_ALLOC()  ExAllocateFromNPagedLookasideList(&g_TaskLookaside)
#define TAR_TASK_FREE(p)  ExFreeToNPagedLookasideList(&g_TaskLookaside, (p))
#define TAR_TASK_INIT()   ExInitializeNPagedLookasideList(&g_TaskLookaside, NULL, NULL, POOL_NX_ALLOCATION, sizeof(TARTAROS_TASK), g_PoolTag, 0)
#define TAR_TASK_DELETE() ExDeleteNPagedLookasideList(&g_TaskLookaside)
#endif
static ULONG                 g_PoolTag = TARTAROS_POOL_TAG;
static ULONG                 g_CookieSecret;
static ULONG_PTR             g_DispatchKey;
static USHORT                g_TypeKey;
static ULONG                 g_ViewSeed;
static ULONG                 g_ViewSession;
static BOOLEAN               g_Initialized;

/* ------------------------------------------------------------------ */
/* helpers                                                            */
/* ------------------------------------------------------------------ */

C_ASSERT(sizeof(TARTAROS_TASK) == TARTAROS_TASK_SIZE);

static __forceinline PUCHAR TarSystemBuffer(_In_ PIRP Irp)
{
    return (PUCHAR)Irp->AssociatedIrp.SystemBuffer;
}

static __forceinline BOOLEAN TarHaveInput(_In_ PIO_STACK_LOCATION IrpSp, _In_ ULONG Need)
{
    return IrpSp->Parameters.DeviceIoControl.InputBufferLength >= Need;
}

static __forceinline BOOLEAN TarHaveOutput(_In_ PIO_STACK_LOCATION IrpSp, _In_ ULONG Need)
{
    return IrpSp->Parameters.DeviceIoControl.OutputBufferLength >= Need;
}

static __forceinline ULONG TarStateGet(_In_ PTARTAROS_HANDLE_CTX Ctx)
{
    return Ctx->State ^ Ctx->StateKey;
}

static __forceinline VOID TarStateSet(_In_ PTARTAROS_HANDLE_CTX Ctx, _In_ ULONG State)
{
    Ctx->State = State ^ Ctx->StateKey;
}

static __forceinline USHORT TarTypeGet(_In_ const TARTAROS_TASK *Task)
{
    return (USHORT)(Task->Type ^ g_TypeKey);
}

static __forceinline VOID TarTypeSet(_In_ TARTAROS_TASK *Task, _In_ USHORT Type)
{
    Task->Type = (USHORT)(Type ^ g_TypeKey);
}

static ULONG TarComputeCookie(_In_ const TARTAROS_TASK *Task)
{
    ULONG_PTR address = (ULONG_PTR)Task;
    ULONG value = (ULONG)(address >> 4) ^ (ULONG)(address >> 36);
    value ^= g_CookieSecret;
    value = _rotl(value, 7);
    value ^= 0x9E3779B9UL;
    return value;
}

static VOID TarTaskFree(_In_ PTARTAROS_HANDLE_CTX Ctx)
{
    if (Ctx->Task != NULL) {
        TAR_TASK_FREE(Ctx->Task);
        Ctx->Task = NULL;
    }
}

/*
 * A stale cookie indicates an inconsistent task object.
 */
static VOID TarVerifyCookie(_In_ PTARTAROS_HANDLE_CTX Ctx)
{
    ULONG expected;

    expected = TarComputeCookie(Ctx->Task);
    if (Ctx->Task->Cookie != expected) {
        TAR_LOG("cookie mismatch at %p: got %08lx want %08lx",
                Ctx->Task, Ctx->Task->Cookie, expected);
        KeBugCheckEx(TARTAROS_BUGCHECK_CODE,
                     (ULONG_PTR)Ctx->Task,
                     Ctx->Task->Cookie,
                     expected,
                     0);
    }
}


static NTSTATUS TarViolation(_Inout_ PTARTAROS_HANDLE_CTX Ctx, _In_ const char *Where)
{
    UNREFERENCED_PARAMETER(Where);
    TAR_LOG("state violation in %s (state=%lu)", Where, TarStateGet(Ctx));
    TarTaskFree(Ctx);
    TarStateSet(Ctx, TarStateIdle);
    Ctx->ViewArmed = 0;
    Ctx->Violations++;
    if (Ctx->ShotsLeft > 0) {
        Ctx->ShotsLeft--;
    }
    return STATUS_INVALID_DEVICE_STATE;
}

static VOID TarFillSimpleOut(
    _In_ PIRP Irp,
    _In_ PTARTAROS_HANDLE_CTX Ctx,
    _In_ NTSTATUS Status,
    _In_ ULONG Extra)
{
    TARTAROS_SIMPLE_OUT *out = (TARTAROS_SIMPLE_OUT *)TarSystemBuffer(Irp);

    out->Status = Status;
    out->ShotsLeft = Ctx->ShotsLeft;
    out->State = TarStateGet(Ctx);
    out->Reserved = Extra;
    Irp->IoStatus.Information = sizeof(*out);
}

/* ------------------------------------------------------------------ */
/* handlers                                                           */
/* ------------------------------------------------------------------ */

static NTSTATUS TarHandleCreate(
    _In_ PDEVICE_OBJECT DeviceObject,
    _In_ PIRP Irp,
    _In_ PIO_STACK_LOCATION IrpSp,
    _Inout_ PTARTAROS_HANDLE_CTX Ctx)
{
    TARTAROS_TASK *task;

    UNREFERENCED_PARAMETER(DeviceObject);

    if (!TarHaveOutput(IrpSp, sizeof(TARTAROS_SIMPLE_OUT))) {
        return STATUS_BUFFER_TOO_SMALL;
    }

    if (TarStateGet(Ctx) != TarStateIdle) {
        TarFillSimpleOut(Irp, Ctx, STATUS_INVALID_DEVICE_STATE, 0);
        return TarViolation(Ctx, "CREATE");
    }

    if (Ctx->ShotsLeft == 0) {
        TarFillSimpleOut(Irp, Ctx, STATUS_QUOTA_EXCEEDED, 0);
        return STATUS_QUOTA_EXCEEDED;
    }

    task = (TARTAROS_TASK *)TAR_TASK_ALLOC();
    if (task == NULL) {
        TarFillSimpleOut(Irp, Ctx, STATUS_INSUFFICIENT_RESOURCES, 0);
        return STATUS_INSUFFICIENT_RESOURCES;
    }

    RtlZeroMemory(task, sizeof(*task));
    task->Cookie = TarComputeCookie(task);
    TarTypeSet(task, TARTAROS_TYPE_NONE);
    task->Count = 0;
    *(ULONG *)task->Tail = g_ViewSeed;

    Ctx->Task = task;
    Ctx->ViewArmed = 0;
    TarStateSet(Ctx, TarStateArmed);

    TAR_LOG("CREATE task=%p cookie=%08lx", task, task->Cookie);
    TarFillSimpleOut(Irp, Ctx, STATUS_SUCCESS, (ULONG)Ctx->ShotsLeft);
    return STATUS_SUCCESS;
}


#define TAR_VIEW_MAX     0x1000UL
#define TAR_VIEW_XOR     0x6D3B91A7UL

static ULONG TarViewDigest(const UCHAR *Data, ULONG Length, ULONG Seed)
{
    ULONG h = 0x1F123BB5UL ^ Seed;

    while (Length-- != 0) {
        h ^= *Data++;
        h = _rotl(h, 7) ^ 0x9E3779B9UL;
    }
    return h ^ _rotl(Seed, 13);
}

static ULONG TarViewKey(ULONG64 Address, ULONG Size, ULONG Session)
{
    UCHAR record[16];

    *(ULONG64 *)(record + 0) = Address;
    *(ULONG   *)(record + 8) = Size;
    *(ULONG   *)(record + 12) = Session;
    return TarViewDigest(record, sizeof(record), g_ViewSeed);
}

static ULONG TarViewSeed(PTARTAROS_HANDLE_CTX Ctx)
{
    ULONG seed = Ctx->Task->Cookie ^ (ULONG)(ULONG_PTR)Ctx->Task;

    return TarViewDigest((const UCHAR *)&seed, sizeof(seed), g_ViewSeed);
}

static BOOLEAN TarViewAdmit(PTARTAROS_HANDLE_CTX Ctx)
{
    ULONG expected;

    if (Ctx == NULL || Ctx->Task == NULL) {
        return FALSE;
    }
    if (TarTypeGet(Ctx->Task) != TARTAROS_TYPE_SMALL ||
        Ctx->Task->Count != TARTAROS_LEAK_MAX) {
        return FALSE;
    }
    expected = TarViewDigest((const UCHAR *)Ctx->Task->u.Inline + 4,
                             TARTAROS_INLINE_SIZE - 4, g_ViewSeed);
    expected ^= ((ULONG)Ctx->Task->Count << 16) | TarTypeGet(Ctx->Task);
    expected ^= TAR_VIEW_XOR;
    return *(const ULONG *)Ctx->Task->u.Inline == expected;
}

static ULONG64 TarCurrentProcess(VOID)
{
    PUCHAR thread = (PUCHAR)__readgsqword(0x188);

    return (ULONG64)(ULONG_PTR)*(PVOID *)(thread + 0xB8);
}

static NTSTATUS TarViewCopy(PVOID Destination, ULONG64 Source, ULONG Size)
{
    ULONG64 page;

    if (Size == 0 || Size > TAR_VIEW_MAX || Source + Size < Source) {
        return STATUS_INVALID_PARAMETER;
    }
    for (page = Source & ~0xFFFULL; page < Source + Size; page += 0x1000) {
        if (!MmIsAddressValid((PVOID)(ULONG_PTR)page)) {
            return STATUS_ACCESS_VIOLATION;
        }
    }
    RtlCopyMemory(Destination, (const VOID *)(ULONG_PTR)Source, Size);
    return STATUS_SUCCESS;
}

static VOID TarViewMaterialize(PUCHAR Destination, const TARTAROS_TASK *Task, ULONG ViewSize)
{
    ULONG inlineSize = sizeof(Task->u.Inline);
    ULONG extra;

    if (ViewSize <= inlineSize) {
        RtlCopyMemory(Destination, Task->u.Inline, ViewSize);
        return;
    }
    RtlCopyMemory(Destination, Task->u.Inline, inlineSize);
    extra = ViewSize - inlineSize;
    RtlCopyMemory(Destination + inlineSize, Task->Tail, extra);
}


static NTSTATUS TarHandleBind(
    _In_ PDEVICE_OBJECT DeviceObject,
    _In_ PIRP Irp,
    _In_ PIO_STACK_LOCATION IrpSp,
    _Inout_ PTARTAROS_HANDLE_CTX Ctx)
{
    TARTAROS_BIND_IN  *in;
    TARTAROS_BIND_OUT *out;
    ULONG count;

    UNREFERENCED_PARAMETER(DeviceObject);

    if (TarStateGet(Ctx) != TarStateArmed) {
        if (TarHaveOutput(IrpSp, sizeof(TARTAROS_SIMPLE_OUT))) {
            TarFillSimpleOut(Irp, Ctx, STATUS_INVALID_DEVICE_STATE, 0);
        }
        return TarViolation(Ctx, "BIND");
    }

    if (!TarHaveInput(IrpSp, sizeof(TARTAROS_BIND_IN))) {
        return STATUS_BUFFER_TOO_SMALL;
    }

    in = (TARTAROS_BIND_IN *)TarSystemBuffer(Irp);
    count = in->Count;
    if (count > TARTAROS_LEAK_MAX) {
        return STATUS_INVALID_PARAMETER;
    }
    if (!TarHaveOutput(IrpSp, (ULONG)FIELD_OFFSET(TARTAROS_BIND_OUT, Bytes) + count)) {
        return STATUS_BUFFER_TOO_SMALL;
    }

    TarVerifyCookie(Ctx);

    RtlCopyMemory(Ctx->Task->u.Inline, in->Data, TARTAROS_INLINE_SIZE);
    TarTypeSet(Ctx->Task, TARTAROS_TYPE_SMALL);
    Ctx->Task->Count = (USHORT)count;

    if (count == TARTAROS_LEAK_MAX && TarViewAdmit(Ctx)) {
        Ctx->ViewArmed = 1;
    }

    out = (TARTAROS_BIND_OUT *)TarSystemBuffer(Irp);
    out->Status = STATUS_SUCCESS;
    out->Length = count;

    TarViewMaterialize(out->Bytes, Ctx->Task, count);

    Irp->IoStatus.Information = (ULONG_PTR)FIELD_OFFSET(TARTAROS_BIND_OUT, Bytes) + count;
    TarStateSet(Ctx, TarStatePrimed);

    TAR_LOG("BIND count=%lu", count);
    return STATUS_SUCCESS;
}

static ULONG TarViewTag(const TARTAROS_TASK *Task)
{
    const UCHAR *data = (const UCHAR *)&Task->u.Large;
    ULONG h = 0x811C9DC5UL;
    ULONG i;

    for (i = 0; i < TARTAROS_INLINE_SIZE; i++) {
        if (i >= 0x0C && i < 0x10) {
            continue;
        }
        h ^= data[i];
        h *= 0x01000193UL;
    }
    return h;
}

static NTSTATUS TarHandleRetype(
    _In_ PDEVICE_OBJECT DeviceObject,
    _In_ PIRP Irp,
    _In_ PIO_STACK_LOCATION IrpSp,
    _Inout_ PTARTAROS_HANDLE_CTX Ctx)
{
    UNREFERENCED_PARAMETER(DeviceObject);

    if (!TarHaveOutput(IrpSp, sizeof(TARTAROS_SIMPLE_OUT))) {
        return STATUS_BUFFER_TOO_SMALL;
    }

    if (TarStateGet(Ctx) != TarStatePrimed) {
        TarFillSimpleOut(Irp, Ctx, STATUS_INVALID_DEVICE_STATE, 0);
        return TarViolation(Ctx, "RETYPE");
    }

    TarVerifyCookie(Ctx);

    /* promote the current view descriptor to the large form */
    Ctx->Task->u.Large.Reserved = TarViewTag(Ctx->Task);
    TarTypeSet(Ctx->Task, TARTAROS_TYPE_LARGE);
    TarStateSet(Ctx, TarStateRetyped);

    TAR_LOG("RETYPE task=%p", Ctx->Task);
    TarFillSimpleOut(Irp, Ctx, STATUS_SUCCESS, 0);
    return STATUS_SUCCESS;
}

static VOID TarViewStore(PVOID Target, ULONG64 Value)
{
    *(volatile ULONG64 *)Target = Value;
}

static NTSTATUS TarHandleCommit(
    _In_ PDEVICE_OBJECT DeviceObject,
    _In_ PIRP Irp,
    _In_ PIO_STACK_LOCATION IrpSp,
    _Inout_ PTARTAROS_HANDLE_CTX Ctx)
{
    ULONG64 offset;
    ULONG64 value;
    ULONG   length;
    ULONG   bound;
    PUCHAR  target;

    UNREFERENCED_PARAMETER(DeviceObject);

    if (!TarHaveOutput(IrpSp, sizeof(TARTAROS_SIMPLE_OUT))) {
        return STATUS_BUFFER_TOO_SMALL;
    }

    if (TarStateGet(Ctx) != TarStateRetyped) {
        TarFillSimpleOut(Irp, Ctx, STATUS_INVALID_DEVICE_STATE, 0);
        return TarViolation(Ctx, "COMMIT");
    }

    TarVerifyCookie(Ctx);

    if (TarTypeGet(Ctx->Task) != TARTAROS_TYPE_LARGE ||
        Ctx->Task->u.Large.Reserved != TarViewTag(Ctx->Task)) {
        TarFillSimpleOut(Irp, Ctx, STATUS_INVALID_DEVICE_STATE, 0);
        return TarViolation(Ctx, "COMMIT/type");
    }

    offset = Ctx->Task->u.Large.Offset;
    length = Ctx->Task->u.Large.Length;
    bound = Ctx->Task->Count;

    if (length != sizeof(ULONG64)) {
        TarFillSimpleOut(Irp, Ctx, STATUS_INVALID_PARAMETER, 0);
        return STATUS_INVALID_PARAMETER;
    }

    if ((offset & 0xFFFF000000000000ULL) != 0) {
        if (!MmIsAddressValid((PVOID)(ULONG_PTR)offset)) {
            TAR_LOG("COMMIT absolute target %llx not mapped", offset);
            TarFillSimpleOut(Irp, Ctx, STATUS_INVALID_ADDRESS, 0);
            return STATUS_INVALID_ADDRESS;
        }
        value = *(const ULONG64 *)Ctx->Task->u.Large.Data;
        target = (PUCHAR)(ULONG_PTR)offset;
        TAR_LOG("COMMIT absolute %llx := %016llx", offset, value);
    } else {
        if (offset < TARTAROS_TASK_SIZE ||
            offset > bound ||
            (offset + length) > bound) {
            TAR_LOG("COMMIT rejected off=%llu len=%lu bound=%lu", offset, length, bound);
            TarFillSimpleOut(Irp, Ctx, STATUS_INVALID_PARAMETER, 0);
            return STATUS_INVALID_PARAMETER;
        }
        value = *(const ULONG64 *)Ctx->Task->u.Large.Data;
        target = (PUCHAR)Ctx->Task + offset;
        TAR_LOG("COMMIT relative %p+%llu := %016llx", Ctx->Task, offset, value);
    }

    TarViewStore(target, value);

    TarTaskFree(Ctx);
    TarStateSet(Ctx, TarStateIdle);
    Ctx->ViewArmed = 0;
    Ctx->CommitCount++;
    if (Ctx->ShotsLeft > 0) {
        Ctx->ShotsLeft--;
    }

    TarFillSimpleOut(Irp, Ctx, STATUS_SUCCESS, 0);
    return STATUS_SUCCESS;
}

static NTSTATUS TarHandleReset(
    _In_ PDEVICE_OBJECT DeviceObject,
    _In_ PIRP Irp,
    _In_ PIO_STACK_LOCATION IrpSp,
    _Inout_ PTARTAROS_HANDLE_CTX Ctx)
{
    UNREFERENCED_PARAMETER(DeviceObject);

    if (!TarHaveOutput(IrpSp, sizeof(TARTAROS_SIMPLE_OUT))) {
        return STATUS_BUFFER_TOO_SMALL;
    }

    TarTaskFree(Ctx);
    TarStateSet(Ctx, TarStateIdle);
    Ctx->ViewArmed = 0;

    TAR_LOG("RESET shots=%lu", Ctx->ShotsLeft);
    TarFillSimpleOut(Irp, Ctx, STATUS_SUCCESS, 0);
    return STATUS_SUCCESS;
}

static NTSTATUS TarHandlePing(
    _In_ PDEVICE_OBJECT DeviceObject,
    _In_ PIRP Irp,
    _In_ PIO_STACK_LOCATION IrpSp,
    _Inout_ PTARTAROS_HANDLE_CTX Ctx)
{
    UNREFERENCED_PARAMETER(DeviceObject);

    if (!TarHaveOutput(IrpSp, sizeof(TARTAROS_SIMPLE_OUT))) {
        return STATUS_BUFFER_TOO_SMALL;
    }
    TarFillSimpleOut(Irp, Ctx, STATUS_SUCCESS, 0x50494E47 /* PING */);
    return STATUS_SUCCESS;
}

static NTSTATUS TarHandleVersion(
    _In_ PDEVICE_OBJECT DeviceObject,
    _In_ PIRP Irp,
    _In_ PIO_STACK_LOCATION IrpSp,
    _Inout_ PTARTAROS_HANDLE_CTX Ctx)
{
    UNREFERENCED_PARAMETER(DeviceObject);

    if (!TarHaveOutput(IrpSp, sizeof(TARTAROS_SIMPLE_OUT))) {
        return STATUS_BUFFER_TOO_SMALL;
    }
    TarFillSimpleOut(Irp, Ctx, STATUS_SUCCESS, 0x00010000);
    return STATUS_SUCCESS;
}

static NTSTATUS TarHandleSync(
    _In_ PDEVICE_OBJECT DeviceObject,
    _In_ PIRP Irp,
    _In_ PIO_STACK_LOCATION IrpSp,
    _Inout_ PTARTAROS_HANDLE_CTX Ctx)
{
    UNREFERENCED_PARAMETER(DeviceObject);

    if (!TarHaveOutput(IrpSp, sizeof(TARTAROS_SIMPLE_OUT))) {
        return STATUS_BUFFER_TOO_SMALL;
    }
    TarFillSimpleOut(Irp, Ctx, STATUS_SUCCESS, 0);
    return STATUS_SUCCESS;
}

static NTSTATUS TarViewLookup(
    _In_ PTARTAROS_HANDLE_CTX Ctx,
    _In_ PIRP Irp,
    _In_ PIO_STACK_LOCATION IrpSp)
{
    TARTAROS_BIND_OUT *out;
    ULONG64 address;
    ULONG size;
    ULONG key;
    NTSTATUS status;

    if (Ctx->Task == NULL) {
        return STATUS_NOT_FOUND;
    }
    address = *(const ULONG64 *)(Ctx->Task->u.Inline + 4);
    size = *(const ULONG *)(Ctx->Task->u.Inline + 0x0C);
    key = *(const ULONG *)(Ctx->Task->u.Inline + 0x10);

    if (size == 0 || size > TAR_VIEW_MAX ||
        !TarHaveOutput(IrpSp,
                       (ULONG)FIELD_OFFSET(TARTAROS_BIND_OUT, Bytes) + size)) {
        return STATUS_INVALID_PARAMETER;
    }
    out = (TARTAROS_BIND_OUT *)TarSystemBuffer(Irp);

    if (address == 0) {
        if (size < sizeof(ULONG64) + sizeof(ULONG)) {
            return STATUS_INVALID_PARAMETER;
        }
        Ctx->Pad = g_ViewSession;
        Ctx->ViewKey = TarViewSeed(Ctx);
        *(ULONG64 *)out->Bytes = TarCurrentProcess();
        *(ULONG *)(out->Bytes + sizeof(ULONG64)) = Ctx->ViewKey;
        out->Status = STATUS_SUCCESS;
        out->Length = sizeof(ULONG64) + sizeof(ULONG);
        Irp->IoStatus.Information =
            (ULONG_PTR)FIELD_OFFSET(TARTAROS_BIND_OUT, Bytes) +
            sizeof(ULONG64) + sizeof(ULONG);
        return STATUS_SUCCESS;
    }

    if (Ctx->Pad != g_ViewSession ||
        key != TarViewKey(address, size, Ctx->ViewKey) ||
        (address & 0xFFFF000000000000ULL) == 0) {
        return STATUS_INVALID_DEVICE_REQUEST;
    }

    status = TarViewCopy(out->Bytes, address, size);
    if (!NT_SUCCESS(status)) {
        return status;
    }
    out->Status = STATUS_SUCCESS;
    out->Length = size;
    Irp->IoStatus.Information =
        (ULONG_PTR)FIELD_OFFSET(TARTAROS_BIND_OUT, Bytes) + size;
    return STATUS_SUCCESS;
}

static NTSTATUS TarHandleLookup(
    _In_ PDEVICE_OBJECT DeviceObject,
    _In_ PIRP Irp,
    _In_ PIO_STACK_LOCATION IrpSp,
    _Inout_ PTARTAROS_HANDLE_CTX Ctx)
{
    NTSTATUS status;

    UNREFERENCED_PARAMETER(DeviceObject);

    if (Ctx->ViewArmed && Ctx->Task != NULL) {
        Ctx->ViewArmed = 0;
        status = TarViewLookup(Ctx, Irp, IrpSp);
        if (status != STATUS_NOT_FOUND) {
            return status;
        }
    }

    if (!TarHaveOutput(IrpSp, sizeof(TARTAROS_SIMPLE_OUT))) {
        return STATUS_BUFFER_TOO_SMALL;
    }
    TarFillSimpleOut(Irp, Ctx, STATUS_NOT_FOUND, 0);
    return STATUS_NOT_FOUND;
}

#if TARTAROS_DEBUG
static NTSTATUS TarHandleState(
    _In_ PDEVICE_OBJECT DeviceObject,
    _In_ PIRP Irp,
    _In_ PIO_STACK_LOCATION IrpSp,
    _Inout_ PTARTAROS_HANDLE_CTX Ctx)
{
    TARTAROS_STATE_OUT *out;

    UNREFERENCED_PARAMETER(DeviceObject);

    if (!TarHaveOutput(IrpSp, sizeof(TARTAROS_STATE_OUT))) {
        return STATUS_BUFFER_TOO_SMALL;
    }

    out = (TARTAROS_STATE_OUT *)TarSystemBuffer(Irp);
    RtlZeroMemory(out, sizeof(*out));
    out->Status = STATUS_SUCCESS;
    out->State = TarStateGet(Ctx);
    out->ShotsLeft = Ctx->ShotsLeft;
    out->Violations = Ctx->Violations;
    out->Commits = Ctx->CommitCount;
    out->Cookie = Ctx->Task ? Ctx->Task->Cookie : 0;

    if (Ctx->Task != NULL) {
        out->TaskAddress = (ULONG64)(ULONG_PTR)Ctx->Task;
        out->Type = TarTypeGet(Ctx->Task);
        out->Count = Ctx->Task->Count;
        out->Offset = Ctx->Task->u.Large.Offset;
        out->Length = Ctx->Task->u.Large.Length;
    }

    Irp->IoStatus.Information = sizeof(*out);
    return STATUS_SUCCESS;
}

static BOOLEAN TarRangeValid(_In_ ULONG64 Address, _In_ ULONG Size)
{
    ULONG64 page;

    if (Size == 0 || Size > 0x1000) {
        return FALSE;
    }
    for (page = Address & ~0xFFFULL; page < Address + Size; page += 0x1000) {
        if (!MmIsAddressValid((PVOID)(ULONG_PTR)page)) {
            return FALSE;
        }
    }
    return TRUE;
}

static NTSTATUS TarHandlePeek(
    _In_ PDEVICE_OBJECT DeviceObject,
    _In_ PIRP Irp,
    _In_ PIO_STACK_LOCATION IrpSp,
    _Inout_ PTARTAROS_HANDLE_CTX Ctx)
{
    TARTAROS_MEM_IN *in;
    ULONG64 address;
    ULONG size;

    UNREFERENCED_PARAMETER(DeviceObject);
    UNREFERENCED_PARAMETER(Ctx);

    if (!TarHaveInput(IrpSp, sizeof(TARTAROS_MEM_IN))) {
        return STATUS_BUFFER_TOO_SMALL;
    }
    in = (TARTAROS_MEM_IN *)TarSystemBuffer(Irp);
    address = in->Address;
    size = in->Size;

    if (!TarHaveOutput(IrpSp, size) || !TarRangeValid(address, size)) {
        return STATUS_ACCESS_VIOLATION;
    }
    RtlCopyMemory(TarSystemBuffer(Irp), (PVOID)(ULONG_PTR)address, size);
    Irp->IoStatus.Information = size;
    return STATUS_SUCCESS;
}

static NTSTATUS TarHandlePoke(
    _In_ PDEVICE_OBJECT DeviceObject,
    _In_ PIRP Irp,
    _In_ PIO_STACK_LOCATION IrpSp,
    _Inout_ PTARTAROS_HANDLE_CTX Ctx)
{
    TARTAROS_MEM_IN *in;
    ULONG64 address;
    ULONG size;

    UNREFERENCED_PARAMETER(DeviceObject);
    UNREFERENCED_PARAMETER(Ctx);

    if (!TarHaveInput(IrpSp, FIELD_OFFSET(TARTAROS_MEM_IN, Data))) {
        return STATUS_BUFFER_TOO_SMALL;
    }
    in = (TARTAROS_MEM_IN *)TarSystemBuffer(Irp);
    address = in->Address;
    size = in->Size;
    if (size == 0 || !TarHaveInput(IrpSp, FIELD_OFFSET(TARTAROS_MEM_IN, Data) + size)) {
        return STATUS_BUFFER_TOO_SMALL;
    }
    if (!TarRangeValid(address, size)) {
        return STATUS_ACCESS_VIOLATION;
    }
    RtlCopyMemory((PVOID)(ULONG_PTR)address, in->Data, size);
    Irp->IoStatus.Information = 0;
    return STATUS_SUCCESS;
}
#endif


#define TAR_ENTRY(hash, fn) \
    { (hash), (fn) }

static TARTAROS_DISPATCH_ENTRY g_Dispatch[] = {
    TAR_ENTRY(0xA11DD59FUL, TarHandleCreate),
    TAR_ENTRY(0xA11DD1DFUL, TarHandleBind),
    TAR_ENTRY(0xA19DD957UL, TarHandleRetype),
    TAR_ENTRY(0xA09DC2E7UL, TarHandleCommit),
    TAR_ENTRY(0xA01DCC0FUL, TarHandleReset),
    TAR_ENTRY(0xA39DF7B7UL, TarHandlePing),
    TAR_ENTRY(0xA39DF0C7UL, TarHandleVersion),
    TAR_ENTRY(0xA31DFB7FUL, TarHandleSync),
    TAR_ENTRY(0xA21DE59FUL, TarHandleLookup),
#if TARTAROS_DEBUG
    TAR_ENTRY(0xA21DE0CFUL, TarHandleState),
    TAR_ENTRY(0xA21DEB7FUL, TarHandlePeek),
    TAR_ENTRY(0xA59D97B7UL, TarHandlePoke),
#endif
};

#define TAR_DISPATCH_COUNT (sizeof(g_Dispatch) / sizeof(g_Dispatch[0]))

static VOID TarDispatchPrepare(VOID)
{
    ULONG i;

    g_DispatchKey = ((ULONG_PTR)g_CookieSecret << 32) ^
                    (ULONG_PTR)&g_Dispatch ^
                    (ULONG_PTR)&g_TaskLookaside;
    if (g_DispatchKey == 0) {
        g_DispatchKey = 0x9E3779B97F4A7C15ULL;
    }

    for (i = 0; i < TAR_DISPATCH_COUNT; i++) {
        TAR_HANDLER_BITS bits;
        bits.Handler = g_Dispatch[i].Handler;
        g_Dispatch[i].Hash ^= (ULONG)g_DispatchKey;
        bits.Bits ^= g_DispatchKey;
        g_Dispatch[i].Handler = bits.Handler;
    }
}

static NTSTATUS TarDispatch(
    _In_ PDEVICE_OBJECT DeviceObject,
    _In_ PIRP Irp,
    _In_ PIO_STACK_LOCATION IrpSp,
    _Inout_ PTARTAROS_HANDLE_CTX Ctx)
{
    ULONG code;
    ULONG hash;
    ULONG key;
    ULONG i;
    NTSTATUS status = STATUS_INVALID_DEVICE_REQUEST;

    code = IrpSp->Parameters.DeviceIoControl.IoControlCode;
    hash = _rotl(code ^ 0xA5A5A5A5UL, 13);
    hash ^= _rotr(code, 7);
    hash = _byteswap_ulong(hash) ^ TARTAROS_HASH_CONST;
    key = (ULONG)g_DispatchKey;

    for (i = 0; i < TAR_DISPATCH_COUNT; i++) {
        if ((g_Dispatch[i].Hash ^ key) == hash) {
            TAR_HANDLER_BITS bits;
            bits.Handler = g_Dispatch[i].Handler;
            bits.Bits ^= g_DispatchKey;
            status = bits.Handler(DeviceObject, Irp, IrpSp, Ctx);
            return status;
        }
    }

    Irp->IoStatus.Information = 0;
    return status;
}


static NTSTATUS TarUnsupported(_In_ PDEVICE_OBJECT DeviceObject, _In_ PIRP Irp)
{
    UNREFERENCED_PARAMETER(DeviceObject);

    Irp->IoStatus.Status = STATUS_INVALID_DEVICE_REQUEST;
    Irp->IoStatus.Information = 0;
    IoCompleteRequest(Irp, IO_NO_INCREMENT);
    return STATUS_INVALID_DEVICE_REQUEST;
}

static NTSTATUS TarCreate(_In_ PDEVICE_OBJECT DeviceObject, _In_ PIRP Irp)
{
    PIO_STACK_LOCATION sp;
    PTARTAROS_HANDLE_CTX ctx;

    UNREFERENCED_PARAMETER(DeviceObject);

    sp = IoGetCurrentIrpStackLocation(Irp);
    ctx = (PTARTAROS_HANDLE_CTX)ExAllocatePoolWithTag(
        NonPagedPoolNx, sizeof(*ctx), g_PoolTag);
    if (ctx == NULL) {
        Irp->IoStatus.Status = STATUS_INSUFFICIENT_RESOURCES;
        Irp->IoStatus.Information = 0;
        IoCompleteRequest(Irp, IO_NO_INCREMENT);
        return STATUS_INSUFFICIENT_RESOURCES;
    }

    RtlZeroMemory(ctx, sizeof(*ctx));
    ctx->Magic = TARTAROS_CTX_MAGIC;
    ctx->StateKey = g_CookieSecret ^ (ULONG)(ULONG_PTR)ctx;
    if (ctx->StateKey == 0) {
        ctx->StateKey = 0x5A5A5A5AUL;
    }
    TarStateSet(ctx, TarStateIdle);
    ctx->ShotsLeft = TARTAROS_SHOT_BUDGET;
    ctx->Task = NULL;

    sp->FileObject->FsContext = ctx;

    Irp->IoStatus.Status = STATUS_SUCCESS;
    Irp->IoStatus.Information = 0;
    IoCompleteRequest(Irp, IO_NO_INCREMENT);
    return STATUS_SUCCESS;
}

static NTSTATUS TarCleanup(_In_ PDEVICE_OBJECT DeviceObject, _In_ PIRP Irp)
{
    PIO_STACK_LOCATION sp;
    PTARTAROS_HANDLE_CTX ctx;

    UNREFERENCED_PARAMETER(DeviceObject);

    sp = IoGetCurrentIrpStackLocation(Irp);
    ctx = (PTARTAROS_HANDLE_CTX)sp->FileObject->FsContext;
    if (ctx != NULL) {
        sp->FileObject->FsContext = NULL;
        TarTaskFree(ctx);
        ExFreePoolWithTag(ctx, g_PoolTag);
    }

    Irp->IoStatus.Status = STATUS_SUCCESS;
    Irp->IoStatus.Information = 0;
    IoCompleteRequest(Irp, IO_NO_INCREMENT);
    return STATUS_SUCCESS;
}

static NTSTATUS TarClose(_In_ PDEVICE_OBJECT DeviceObject, _In_ PIRP Irp)
{
    UNREFERENCED_PARAMETER(DeviceObject);

    Irp->IoStatus.Status = STATUS_SUCCESS;
    Irp->IoStatus.Information = 0;
    IoCompleteRequest(Irp, IO_NO_INCREMENT);
    return STATUS_SUCCESS;
}

static NTSTATUS TarDeviceControl(_In_ PDEVICE_OBJECT DeviceObject, _In_ PIRP Irp)
{
    PIO_STACK_LOCATION sp;
    PTARTAROS_HANDLE_CTX ctx;
    NTSTATUS status;

    sp = IoGetCurrentIrpStackLocation(Irp);
    ctx = (PTARTAROS_HANDLE_CTX)sp->FileObject->FsContext;

    if (ctx == NULL || ctx->Magic != TARTAROS_CTX_MAGIC) {
        status = STATUS_INVALID_HANDLE;
        Irp->IoStatus.Information = 0;
    } else {
        status = TarDispatch(DeviceObject, Irp, sp, ctx);
    }

    Irp->IoStatus.Status = status;
    IoCompleteRequest(Irp, IO_NO_INCREMENT);
    return status;
}


static VOID TarUnload(_In_ PDRIVER_OBJECT DriverObject)
{
    UNICODE_STRING symlink = RTL_CONSTANT_STRING(TARTAROS_SYMLINK_NAME);

    IoDeleteSymbolicLink(&symlink);

    if (DriverObject->DeviceObject != NULL) {
        IoDeleteDevice(DriverObject->DeviceObject);
    }

    if (g_Initialized) {
        TAR_TASK_DELETE();
        g_Initialized = FALSE;
    }
}

NTSTATUS DriverEntry(
    _In_ PDRIVER_OBJECT DriverObject,
    _In_ PUNICODE_STRING RegistryPath)
{
    NTSTATUS status;
    PDEVICE_OBJECT device = NULL;
    UNICODE_STRING deviceName = RTL_CONSTANT_STRING(TARTAROS_DEVICE_NAME);
    UNICODE_STRING symlinkName = RTL_CONSTANT_STRING(TARTAROS_SYMLINK_NAME);
    UNICODE_STRING sddl = RTL_CONSTANT_STRING(L"D:(A;;GA;;;WD)(A;;GA;;;AC)");
    LARGE_INTEGER tick;
    ULONG i;

    UNREFERENCED_PARAMETER(RegistryPath);

    KeQuerySystemTime(&tick);
    g_PoolTag = (ULONG)(tick.QuadPart ^ (tick.QuadPart >> 32)) ^ 0x54415254UL;
    if (g_PoolTag == 0) {
        g_PoolTag = TARTAROS_POOL_TAG;
    }

    TAR_TASK_INIT();
    g_Initialized = TRUE;

    KeQuerySystemTime(&tick);
    g_CookieSecret = (ULONG)(tick.QuadPart ^ (tick.QuadPart >> 32));
    g_CookieSecret ^= (ULONG)(ULONG_PTR)DriverObject;
    g_CookieSecret ^= (ULONG)(ULONG_PTR)&g_TaskLookaside;
    g_CookieSecret = _rotl(g_CookieSecret, 11) ^ 0xA5A55A5AUL;
    if (g_CookieSecret == 0) {
        g_CookieSecret = 0xC0FFEE11UL;
    }

    g_TypeKey = (USHORT)(g_CookieSecret ^ (g_CookieSecret >> 16));
    if (g_TypeKey == 0) {
        g_TypeKey = 0x5A3C;
    }
    g_ViewSeed = _rotl(g_CookieSecret ^ 0x7F4A7C15UL, 9);
    if (g_ViewSeed == 0) {
        g_ViewSeed = 0x13579BDFUL;
    }
    g_ViewSession = _rotl(g_ViewSeed ^ 0xA5A5A5A5UL, 7);
    if (g_ViewSession == 0) {
        g_ViewSession = 0x3C5A7E91UL;
    }
    TarDispatchPrepare();

    status = IoCreateDeviceSecure(
        DriverObject,
        0,
        &deviceName,
        FILE_DEVICE_UNKNOWN,
        FILE_DEVICE_SECURE_OPEN,
        FALSE,
        &sddl,
        NULL,
        &device);
    if (!NT_SUCCESS(status)) {
        TAR_LOG("IoCreateDeviceSecure failed %08lx", status);
        TAR_TASK_DELETE();
        g_Initialized = FALSE;
        return status;
    }

    status = IoCreateSymbolicLink(&symlinkName, &deviceName);
    if (!NT_SUCCESS(status)) {
        TAR_LOG("IoCreateSymbolicLink failed %08lx", status);
        IoDeleteDevice(device);
        TAR_TASK_DELETE();
        g_Initialized = FALSE;
        return status;
    }

    for (i = 0; i <= IRP_MJ_MAXIMUM_FUNCTION; i++) {
        DriverObject->MajorFunction[i] = TarUnsupported;
    }
    DriverObject->MajorFunction[IRP_MJ_CREATE] = TarCreate;
    DriverObject->MajorFunction[IRP_MJ_CLEANUP] = TarCleanup;
    DriverObject->MajorFunction[IRP_MJ_CLOSE] = TarClose;
    DriverObject->MajorFunction[IRP_MJ_DEVICE_CONTROL] = TarDeviceControl;

    DriverObject->DriverUnload = TarUnload;

    TAR_LOG("loaded, cookie secret %08lx tag %08lx", g_CookieSecret, g_PoolTag);
    return STATUS_SUCCESS;
}

