# CTFCup 2026 — Puzzle (Forensics + Reverse) — полный разбор

**Флаг:**

```
ctfcup{4lpc_r3mn4nts_0f_th3_br0k3r_7hru_p1x3l5}
```

Восстановленное изображение: `artifacts/recovered_flag.png` (941 байт, PNG 343×343, 1-bit grayscale, внутри QR-код).

---

## 0. Что дано и в чём суть таска

Дан единственный файл:

```
Puzzle_CTFCUP-Snapshot7.vmem   2 GiB   (снимок оперативной памяти Windows, VMware .vmem)
```

Сюжет восстанавливается из дампа: на машине пользователя `anon` лежал `flag.png`, который «прогонялся» через набор из пяти программ (`broker.exe` + `cl0..cl3.exe`), после чего PowerShell-скрипт **затирал файл случайными байтами, удалял его** и вызывал `purge.exe`, чтобы вычистить standby-страницы файлового кэша.

То есть на диске (и в кэше) файла уже нет. Но:

1. Сами бинарники и скрипты остались в памяти (как `FILE`-объекты / `DataSectionObject`).
2. Клиенты **читают** файл (открывают его только на чтение — `GENERIC_READ`) и каждый раунд отправляют по IPC сообщение `DATX`, внутри которого лежит **преобразованный чанк файла + CRC32 исходного (непреобразованного) чанка**.
3. Эти `DATX`-сообщения остаются в физической памяти.

Преобразования у всех четырёх клиентов разные, но **обратимые**. Восстановив 4 алгоритма и найдя `DATX`-сообщения в дампе, можно расшифровать чанки, проверить их по CRC32 из заголовка, склеить исходный `flag.png` и прочитать QR-код.

Итоговая цепочка решения:

```
.vmem
  └─ Volatility3: info/pslist/pstree/cmdline
       └─ filescan → FILE-объекты vm-run\vm-run\*
            └─ dumpfiles --virtaddr → orchestrate.ps1, RUN.ps1, broker.exe, cl0..cl3.exe, purge.exe
                 └─ IDA Pro / objdump: реверс протокола CTRL/DATX и 4-х преобразований
                      └─ grep физической памяти по 'CTLX' / 'DATX'
                           └─ расшифровка чанков (4 алгоритма) + проверка CRC32
                                └─ склейка flag.png → zbarimg → флаг
```

---

## 1. Инструменты

| Инструмент | Зачем |
|---|---|
| Volatility 3 (`~/tools/volatility3/vol.py`, v2.26.2) | анализ дампа памяти (`windows.*`) |
| IDA Pro 9.3 + IDA-MCP | реверс `broker.exe`, `cl0/cl1/cl3.exe` |
| `x86_64-w64-mingw32-objdump` | быстрая дизассембляция «сырых» кусков и `cl2.exe` |
| Python 3 (+ `mmap`, `zlib`, `struct`, `Pillow`) | парсинг дампа, расшифровка, сборка PNG |
| `gcc` | брутфорс ключа `cl2.exe` (быстрый RC4) |
| `zbarimg` (zbar) | декодирование QR |

Все команды ниже выполняются из `/root/dev/ctfcup-2026/puzzle/`.

```bash
mkdir -p work bin out artifacts
VOL=~/tools/volatility3/vol.py
DUMP=Puzzle_CTFCUP-Snapshot7.vmem
```

---

## 2. Первичный триаж дампа

Volatility предупреждает, что рядом нет `.vmss/.vmsn` (это нормально для «плоского» `.vmem` — фреймворк сам строит трансляцию):

```bash
python3 $VOL -f $DUMP windows.info
```

```
Kernel Base   0xf80703216000
DTB           0x1a4000
Is64Bit       True
Major/Minor   15.19041          # Windows 10 20H1 / build 19041
SystemTime    2026-10-24 22:37:45+00:00
NtSystemRoot  C:\Windows
```

Список процессов и дерево:

```bash
python3 $VOL -f $DUMP windows.pstree  > work/pstree.txt
python3 $VOL -f $DUMP windows.cmdline > work/cmdline.txt
```

Самое интересное — хвост дерева: `explorer.exe → powershell.exe → broker/cl*/purge`.

```
5436  3496  powershell.exe   0x800492238080
**** 5168  5436  broker.exe      \Device\HarddiskVolume3\Users\anon\Desktop\vm-run\vm-run\broker.exe
****  720  5436  cl0.exe         \Device\HarddiskVolume3\Users\anon\Desktop\vm-run\vm-run\cl0.exe
**** 3144  5436  cl1.exe         \Device\HarddiskVolume3\Users\anon\Desktop\vm-run\vm-run\cl1.exe
**** 4364  5436  cl2.exe         \Device\HarddiskVolume3\Users\anon\Desktop\vm-run\vm-run\cl2.exe
**** 2028  5436  cl3.exe         \Device\HarddiskVolume3\Users\anon\Desktop\vm-run\vm-run\cl3.exe
**** 3912  5436  purge.exe       \Device\HarddiskVolume3\Users\anon\Desktop\vm-run\vm-run\purge.exe
```

`windows.pslist` даёт таймлайн (это важно — снимок сделан через ~3 секунды после завершения всей цепочки):

```
5168  broker.exe   22:37:39  exit 22:37:41
 720  cl0.exe      22:37:40  exit 22:37:40
3144  cl1.exe      22:37:40  exit 22:37:40
4364  cl2.exe      22:37:40  exit 22:37:40
2028  cl3.exe      22:37:40  exit 22:37:40
3912  purge.exe    22:37:42  exit 22:37:42
                   снимок: 22:37:45
```

Все процессы уже завершены (0 потоков), поэтому `windows.memmap --pid <pid> --dump` для них бесполезен: VAD/таблицы страниц освобождены и `memmap` отдаёт мусор другого процесса. Это тупик, который лучше обойти сразу (`windows.dumpfiles --virtaddr` работает, см. ниже).

---

## 3. Почему `strings`/`grep` по «CTFCUP» и PNG-сигнатуре не сработал

Первые проверки по всему дампу:

```bash
grep -aob "CTFCUP" Puzzle_CTFCUP-Snapshot7.vmem | head      # пусто
grep -aobP "\x89PNG\r\n\x1a\n" Puzzle_CTFCUP-Snapshot7.vmem # пусто
```

Почему:

* флаг — это **не текст, а QR-код внутри PNG** (поэтому «ctfcup» в памяти нет);
* исходный PNG на диске был затёрт `RNGCryptoServiceProvider`-мусором и удалён;
* `purge.exe` вычистил standby-страницы (файловый кэш), так что даже сигнатуры файла не осталось;
* единственные копии содержимого файла в RAM — это `DATX`-сообщения, где данные **зашифрованы** (XOR/ROT/xorshift/RC4).

Что всё-таки находится «руками» — исходники скриптов (они хранятся в памяти как обычный текст):

```bash
grep -aob "vm-run\|orchestrate.ps1\|\[1/6\]" Puzzle_CTFCUP-Snapshot7.vmem | head
```

Например, по смещению `357710000` лежит `RUN.ps1`, по `552040000` и `2019050000` — `orchestrate.ps1`.
Но гораздо надёжнее извлечь их как файлы (следующий раздел).

---

## 4. Извлечение файлов из памяти (filescan + dumpfiles)

`windows.filescan` выдаёт адреса `_FILE_OBJECT` вместе с путями:

```bash
python3 $VOL -f $DUMP windows.filescan > work/filescan.txt
grep -i "vm-run" work/filescan.txt
```

```
0x8004920d4b10  \Users\anon\Desktop\vm-run\vm-run\cl1.exe
0x8004923373e0  \Users\anon\Desktop\vm-run\vm-run\cl0.exe
0x800492337a20  \Users\anon\Desktop\vm-run\vm-run\broker.exe
0x8004924281b0  \Users\anon\Desktop\vm-run\vm-run\purge.exe
0x800492432d90  \Users\anon\Desktop\vm-run\vm-run\RUN.ps1
0x800492434690  \Users\anon\Desktop\vm-run\vm-run\orchestrate.ps1
0x800492437a20  \Users\anon\Desktop\vm-run\vm-run\cl3.exe
0x800492438ce0  \Users\anon\Desktop\vm-run\vm-run\cl2.exe
0x800492438e70  \Users\anon\Desktop\vm-run\vm-run\cl1.exe
```

Дампим каждый объект (`--pid` для завершённых процессов не работает, `--virtaddr` — работает):

```bash
mkdir -p work/files
for a in 0x8004920d4b10 0x8004923373e0 0x800492337a20 0x8004924281b0 \
         0x800492432d90 0x800492434690 0x800492437a20 0x800492438ce0 0x800492438e70; do
  python3 $VOL -f $DUMP -o work/files windows.dumpfiles --virtaddr $a
done
ls -la work/files
```

Получаем:

| Файл | Размер | Что внутри |
|---|---|---|
| `...broker.exe.img` | 155648 (0x26000) | `broker.exe`, полноценный PE |
| `...cl0.exe.img` | 109568 (0x1AC00) | `cl0.exe` |
| `...cl1.exe.img` | 109568 | `cl1.exe` |
| `...cl3.exe.img` | 109568 | `cl3.exe` |
| `...cl2.exe.img` | 110080 (0x1AE00) | образ `cl2.exe` **без заголовка** (см. §7) |
| `...purge.exe.img` | 140800 | `purge.exe` |
| `...RUN.ps1.dat` | 4096 | нули (страница вытеснена) |
| `...orchestrate.ps1.dat` | 8192 | полный текст скрипта |

> `RUN.ps1` из `dumpfiles` пришёл нулевым, но его текст был виден в сыром дампе рядом с `flag.png`, так что содержимое восстановлено.

### 4.1. Что делает `orchestrate.ps1`

Ключевые фрагменты:

```powershell
param(
    [string]$ImageFile = '',
    [string]$BinDir  = '',
    [int]$Rounds     = 4,
    ...
)
...
$brokerArgs = @("`"$ImageFile`"", '--rounds', "$Rounds")
...
Write-Host "[1/6] starting broker ..."
$bp = Start-OurProcess $broker $brokerArgs
Write-Host "[2/6] starting cl0..cl3 ..."
foreach ($n in 0..3) { $clients += Start-OurProcess (Join-Path $BinDir "cl$n.exe") @("`"$ImageFile`"") }
...
if (-not $KeepImage) {
    Write-Host "[5/6] securely deleting $ImageFile ..."
    $len = (Get-Item -LiteralPath $ImageFile).Length
    $rng = [System.Security.Cryptography.RNGCryptoServiceProvider]::new()
    $fs = [System.IO.File]::Open($ImageFile, [System.IO.FileMode]::Open,
                                 [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
    ... $fs.Write($buf, 0, [int]$n) ...     # затирание случайными байтами
    Remove-Item -LiteralPath $ImageFile -Force
}
if (-not $SkipPurge) {
    Write-Host "[6/6] purging standby list ..."
    $pp = Start-Process -FilePath $purge -PassThru -NoNewWindow -Wait   # purge.exe
}
```

`RUN.ps1` (восстановлен из сырого дампа) — обёртка, которая запускает всё с `-Rounds 8`:

```powershell
param([int]$Rounds = 8)
$kit  = $PSScriptRoot
$flag = Join-Path $kit 'flag.png'
if (-not (Test-Path -LiteralPath $flag)) {
    throw "flag.png not found here (after a previous final run it is deleted - re-extract the kit)"
}
& (Join-Path $kit 'orchestrate.ps1') -ImageFile $flag -BinDir $kit -Rounds $Rounds
```

А фактические аргументы `broker.exe` видны прямо в памяти (блок параметров процесса, смещение ~`1623749000`):

```
"C:\Users\anon\Desktop\vm-run\vm-run\broker.exe" "...\flag.png" --rounds 8
```

Итого: **8 раундов**, 4 клиента, `-wirelog` не использовался.

---

## 5. Реверс `broker.exe` (IDA Pro)

Открываем в IDA (MCP):

```text
ida_mcp_open_idb(path=".../bin/broker.exe", auto_analyse=true)
```

`start → sub_7FF7A8153A20 → sub_7FF7A81515B0` — это `main` (`0x7FF7A81515B0`).

### 5.1. Аргументы и разбиение на чанки

Из декомпиляции `main`:

```c
v2 = L"flag.png";                 // имя файла по умолчанию
...
v3 = sub_7FF7A81571C8(v12);       // --rounds N  (clamp 1..16)
...
if ( !sub_7FF7A8153310(v2, &v107) || !v107 ) { ... }   // размер файла -> v107
v22 = (v107 + 127) >> 7;                                // chunks = ceil(size/128)
if ( (unsigned int)(v22 - 1) > 0xFFF )                  // максимум 4096 чанков
    ... "broker: unsupported chunk count"
```

Распределение чанков по клиентам — round-robin по номеру чанка:

```c
v51 = (chunk & 3) < 2 ? 0 : ((chunk & 3) == 2 ? 1 : 2);  // "channel"
...
// на каждого клиента:
//   chunks[i]        = число чанков
//   expected_data[i] = chunks[i] * rounds
```

То есть чанк с индексом `i` обрабатывает клиент `i & 3`, а «канал» — производная от него:
клиенты 0/1 общаются через pipe/mailslot, 2/3 — через «канал 1»/«канал 2».

### 5.2. Сообщение CTRL (`CTLX`) — 32 байта

```c
LODWORD(v136) = 1481397315;   // 0x584C5443 = 'CTLX'
HIDWORD(v136) = 1;            // type = 1 (CTRL)
*(_DWORD *)v137       = v48;  // chunk index
*(_DWORD *)&v137[4]   = v48 << 7;       // offset = chunk * 128
*(_DWORD *)&v137[8]   = min(128, size - offset);  // len
LOWORD(v138)          = chunk & 3;      // client id
HIWORD(v138)          = channel;        // 0/1/2
v139                  = 0;
sub_7FF7A8152F10(v29, &v136, 32);       // отправка всем (ALPC broadcast)
```

Затем END и FINISH:

```c
// END:  type = 2, chunk = -1, len = 0, cid = 0xFFFF, ch = 0xFFFF, +24: rounds
v139 = v101;  v136 = 0x2584C5443;  *(_DWORD *)v137 = -1;  v138 = 0xFFFF;

// FINISH: type = 3, chunk = -1, всё нули
v136 = 0x3584C5443;  *(_DWORD *)v137 = -1;  v138 = 0xFFFF;  v139 = 0;
```

Итоговая раскладка CTRL-сообщения (`CTLX`):

| Смещение | Размер | Поле |
|---|---|---|
| 0 | 4 | magic `'CTLX'` (0x584C5443) |
| 4 | 4 | type: 1 = CTRL, 2 = END, 3 = FINISH |
| 8 | 4 | chunk index |
| 12 | 4 | offset в файле |
| 16 | 4 | length (≤128) |
| 20 | 2 | client id |
| 22 | 2 | channel |
| 24 | 8 | для END — число раундов |

### 5.3. Приём данных: `DATX` — 20 байт заголовка + payload

`main` создаёт именованный pipe (`StartAddress`, `0x7FF7A81513D0`), mailslot (`sub_7FF7A8151210`) и 4 ALPC-приёмника (`sub_7FF7A8151010`). Все они проверяют одно и то же:

```c
((void (__fastcall *)(_DWORD *, _QWORD, __int64))qword_7FF7A8167520[0])(Buffer, 0, 0x4000); // memset
if ( NumberOfBytesRead >= 0x14 && Buffer[0] == 1481916740 )   // 'DATX'
{
    v4 = *((_WORD *)lpThreadParameter + 4);                   // ожидаемый client id
    if ( v12 == v4 )                                          // +8  client id
    {
        ...
        if ( v13 == v5                                          // +10 channel
          && (unsigned int)(v14 - 1) <= 0x7F                    // +12 len 1..128
          && NumberOfBytesRead >= v14 + 20
          && NumberOfBytesRead <= 0x1000
          && Buffer[1] < *((_DWORD *)lpThreadParameter + 8) )   // +4 chunk < chunks
        {
            v6 = NumberOfBytesRead;
            v7 = sub_7FF7A8156930(NumberOfBytesRead);           // malloc
            if ( v7 )
                loc_7FF7A8166E70(v7, Buffer, v6);               // memcpy (сохраняет копию!)
            v8 = *((_QWORD *)lpThreadParameter + 5);
            if ( v8 )
                sub_7FF7A81533C0(v8, *((_QWORD *)lpThreadParameter + 6), Buffer, NumberOfBytesRead); // wirelog
            ++*((_DWORD *)lpThreadParameter + 4);               // счётчик
        }
    }
}
```

**Ключевой вывод:** broker только считает пакеты и (опционально) пишет их в wirelog. Он **не пишет файл**. И `DATX` нигде не проверяет CRC — CRC лежит в сообщении «для красоты»/диагностики, но нам он идеально подходит для верификации.

Раскладка `DATX`:

| Смещение | Размер | Поле |
|---|---|---|
| 0 | 4 | magic `'DATX'` (0x58544144) |
| 4 | 4 | chunk index |
| 8 | 2 | client id |
| 10 | 2 | channel |
| 12 | 4 | length (1..128) |
| 16 | 4 | **CRC32 исходного (незашифрованного) чанка** |
| 20 | len | payload — **преобразованные** байты чанка |

---

## 6. Реверс клиентов: четыре разных обратимых преобразования

Клиент (`main` у `cl0` — `sub_7FF7C74F10A0`) делает следующее:

1. открывает `flag.png` **только на чтение**:
   ```c
   CreateFileW(v2, 0x80000000 /*GENERIC_READ*/, 7, 0, 3 /*OPEN_EXISTING*/, 0x80, 0);
   ```
2. читает CTRL-сообщения, собирает таблицу чанков `(idx, offset, len)`;
3. по END (`type == 2`) берёт `rounds` (`v37`, clamp 1..16);
4. в цикле по раундам, для каждого своего чанка:
   ```c
   SetFilePointerEx(hFile, offset, 0, FILE_BEGIN); ReadFile(hFile, buf, len, ...);
   crc = crc32(buf, len);       // CRC32 ДО преобразования
   transform(buf, len);         // преобразование на месте
   // формируется DATX: 'DATX', idx, cid, ch, len, crc, buf[len]
   ```
5. ждёт FINISH (`type == 3`) и выходит.

Так как файл открыт read-only и никто его не пишет, **все 8 раундов читают один и тот же исходный файл**. Поэтому `DATX` всех раундов для одного чанка идентичны и несут один и тот же CRC — файл «шифруется» только в памяти/IPC. Это и есть зацепка: достаточно найти по одному `DATX` на чанк.

### 6.1. `cl0` — повторяющийся XOR

```c
__int64 sub_7FF7C74F1000(__int64 a1, unsigned __int64 a2)
{
  _BYTE v5[16];
  for ( i = 0; i < 0x10; ++i )
    v5[i] = byte_7FF7C74FF328[i] ^ byte_7FF7C74FF328[i + 16];
  for ( j = 0; j < a2; ++j )
    *(_BYTE *)(a1 + j) ^= v5[j & 0xF];
  ...
}
```

32 байта по RVA `0xF328` (адрес `0x7FF7C74FF328` = база `0x7FF7C74F0000`):

```
ea26fc77a683b01f59a9f6786377fb9f 00a8d7cbf8ad7478e5cb9ec8bdfec4f2
```

ключ (первые 16 XOR вторые 16):

```
ea8e2bbc5e2ec467bc6268b0de893f6d
```

Восстановление: `plain[i] = cipher[i] ^ key[i % 16]`.

### 6.2. `cl1` — ROR5 + 0x5A

```asm
; transform @ RVA 0x1000 (0x7FF6C5A31000)
xor    eax,eax
loop:
  movzbl r8d, byte ptr [rax+rcx]   ; rcx = buf
  ror    r8b, 5
  add    r8b, 0x5A
  mov    byte ptr [rax+rcx], r8b
  inc    rax
  cmp    rax, rdx                  ; rdx = len
  jb     loop
```

Обратное: `plain = ROL8((cipher - 0x5A) & 0xFF, 5)`.

### 6.3. `cl3` — xorshift-кейстрим

```asm
; transform @ RVA 0x1000 (0x7FF7C0F91000)
mov  dword [rsp+0x18], 0B037BF34h
mov  dword [rsp+0x10], 6A9B701Ch
mov  eax, [rsp+0x10]
mov  r8d, [rsp+0x18]
xor  eax, r8d                 ; seed = 0x6A9B701C ^ 0xB037BF34
loop:
  mov  ecx, eax
  shl  ecx, 13
  xor  ecx, eax
  mov  edx, ecx
  shr  edx, 17
  xor  edx, ecx
  mov  eax, edx
  shl  eax, 5
  xor  eax, edx
  xor  byte ptr [r8+r9], al    ; buf[i] ^= low byte
  inc  r8
  cmp  r8, r10                 ; r10 = len
  jb   loop
```

То есть `x ^= x<<13; x ^= x>>17; x ^= x<<5; byte ^= x & 0xFF` (все операции 32-битные), генератор стартует заново на каждый чанк. Преобразование — инволюция (повторное применение расшифровывает).

### 6.4. `cl2` — RC4 с 24-байтным ключом

`cl2.exe` извлёкся с «обрезанным» образом (заголовок/первая страница не резидентна), поэтому пришлось разбирать `.text` напрямую. Находим в образе константу `'DATX'`:

```python
d = open('work/files/file.0x800492438ce0...img','rb').read()
d.find(b'DATX')      # -> 0x8e8 (единственное вхождение в образе)
```

Идём назад по `e8` (near call) и получаем две вызова подряд (CRC и transform):

```python
# call at 0x8bb, rel +0x1bd  -> 0xa7d  (CRC32)
# call at 0x8cc, rel -0x4d1  -> 0x400  (transform)
```

Дизассемблируем «сырой» кусок (т.к. `cl2` лежит без заголовка — обычный `objdump -d` не подходит):

```bash
dd if=$(ls work/files/file.0x800492438ce0*) of=/tmp/cl2_text.bin bs=1 skip=1024 count=600
x86_64-w64-mingw32-objdump -D -b binary -m i386:x86-64 -M intel /tmp/cl2_text.bin
```

Получаем классический RC4:

```asm
; KSA
  movzx ecx, byte ptr [r8+rdx+0F340h]     ; key[i]  (rdx = image base)
  movzx eax, byte ptr [r8+rdx+0F328h]
  xor   cl, al
  mov   byte ptr [rsp+r8+20h], cl
  inc   r8
  cmp   r8, 18h                            ; длина ключа 24
  jb    ...
  ; j += S[i] + key[i%24]; swap(S[i],S[j])
; PRGA
  i = (i+1)&0xff; j = (j+S[i])&0xff; swap; buf[k] ^= S[(S[i]+S[j])&0xff]
```

Т.е. ключ = `byte[RVA 0xF340 + i] ^ byte[RVA 0xF328 + i]`, `i = 0..23`.

### 6.5. Как был найден ключ `cl2` (он не лежал там, где ожидалось)

В образе `cl2` по «ожидаемым» адресам лежали таблицы RVA (0x188a0, 0x188ae, …) — видимо, из-за иной раскладки секций/смещения образа. CRC-проверка отбросила неверные варианты, поэтому ключ был найден прямым перебором: предполагаем, что две 24-байтные «половинки» лежат в образе на фиксированном расстоянии `delta` друг от друга, строим ключ как XOR и проверяем RC4 по CRC32 чанка.

Брутфорс на C (быстро, ~секунды на 2 ГБ не нужен — только образ 110 КБ):

```c
// /tmp/brutekey.c — см. полный листинг в Приложении B
// argv[1] = образ cl2, argv[2] = 128-байтный ciphertext чанка,
// argv[3] = ожидаемый CRC32 из заголовка DATX
```

```bash
# вытаскиваем ciphertext чанка 2 (client 2) из дампа
python3 - <<'PY'
import mmap, struct
f = open('Puzzle_CTFCUP-Snapshot7.vmem','rb'); mm = mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ)
magic, idx, cid, ch, ln, crc = struct.unpack('<IIHHII', mm[177007736:177007756])
open('/tmp/ct2.bin','wb').write(mm[177007756:177007756+ln])
print(idx, cid, ln, crc)
PY

/tmp/brutekey $(ls work/files/file.0x800492438ce0*) /tmp/ct2.bin 2549867187
```

```
delta 16 done
...
FOUND o=58664 delta=24 key=7035486a586e752d6b4372656b496a5f624c7a6949346157
      plain=dfc47e5eafdcccecd238fb89ed244909 off=e528
```

Ключ — ASCII-строка из 24 байт:

```
p5HjXnu-kCrekIj_bLziI4aW
```

(смещение `0xE528` и `0xE540` в образе, `delta = 0x18`).

> Замечание: CRC32 совпал — вероятность случайного совпадения ~2⁻³², так что ключ подтверждён независимо от дизассемблера.

---

## 7. Поиск `DATX` в физической памяти и восстановление таблицы чанков

Ищем в сыром дампе сигнатуры `CTLX` и `DATX` (`mmap` + `find` побайтно, 2 ГБ ~ несколько секунд):

```python
import mmap, struct
f = open('Puzzle_CTFCUP-Snapshot7.vmem','rb')
mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)

i, msgs = 0, []
while True:
    i = mm.find(b'CTLX', i)
    if i < 0: break
    magic, typ, idx, off, ln, cid, ch, extra = struct.unpack('<IIIIIHHQ', mm[i:i+32])
    if typ in (1,2,3) and ln <= 128 and idx < 100000 and off < 100_000_000:
        msgs.append((i, typ, idx, off, ln, cid, ch, extra))
    i += 1
for m in msgs: print(m)
```

Восстановленная таблица чанков (все CTRL-сообщения сходятся):

```
idx=0 off=0   len=128 cid=0 ch=0
idx=1 off=128 len=128 cid=1 ch=0
idx=2 off=256 len=128 cid=2 ch=1
idx=3 off=384 len=128 cid=3 ch=2
idx=4 off=512 len=128 cid=0 ch=0
idx=5 off=640 len=128 cid=1 ch=0
idx=6 off=768 len=128 cid=2 ch=1
idx=7 off=896 len=45  cid=3 ch=2
```

Отсюда сразу получаем **размер файла**: `896 + 45 = 941` байт.

Аналогично парсим `DATX` (фильтруя случайные совпадения по разумным полям):

```python
i = 0
while True:
    i = mm.find(b'DATX', i)
    if i < 0: break
    if i + 20 <= len(mm):
        magic, idx, cid, ch, ln, crc = struct.unpack('<IIHHII', mm[i:i+20])
        if ln and 1 <= ln <= 128 and idx < 8 and cid < 4 and ch < 3:
            print(hex(i), idx, cid, ch, ln, crc)
    i += 1
```

Найденные «настоящие» сообщения (по одному представителю на чанк):

| chunk | client | file offset в дампе | len | CRC32 из заголовка |
|---|---|---|---|---|
| 0 | 0 | `0x08B66C78` | 128 | 1797098371 |
| 1 | 1 | `0x08B07C78` | 128 | 3405870171 |
| 2 | 2 | `0x0A8CEC78` | 128 | 2549867187 |
| 3 | 3 | `0x0A028C78` | 128 | 2031548828 |
| 4 | 0 | `0x08B05C78` | 128 | 1684294195 |
| 5 | 1 | `0x168D1C78` | 128 | 2453593637 |
| 6 | 2 | `0x0633CC78` | 128 | 2781267344 |
| 7 | 3 | `0x0BA33C78` | 45  | 3956758277 |

(Смещения могут отличаться при повторном проходе — их много, по несколько копий на чанк; берётся любой, CRC у всех одинаковый.)

---

## 8. Расшифровка и сборка `flag.png`

Полный скрипт (Приложение A) делает:

1. находит все `DATX`;
2. для `cid` 0..3 применяет обратное преобразование;
3. проверяет `zlib.crc32(plain) == crc_from_header`;
4. берёт первый успешный чанк для каждого `idx = 0..7`;
5. склеивает по порядку.

Ключевые функции:

```python
def ror8(v, n): return ((v >> n) | (v << (8 - n))) & 0xFF
def rol8(v, n): return ((v << n) | (v >> (8 - n))) & 0xFF

KEY0 = bytes.fromhex('ea8e2bbc5e2ec467bc6268b0de893f6d')

def dec_cl0(d):  # XOR с 16-байтным ключом
    return bytes(d[i] ^ KEY0[i % 16] for i in range(len(d)))

def dec_cl1(d):  # обратное ROR5 + 0x5A
    return bytes(rol8((x - 0x5A) & 0xFF, 5) for x in d)

def rc4(key, data):
    S = list(range(256)); j = 0
    for i in range(256):
        j = (j + S[i] + key[i % len(key)]) & 0xFF
        S[i], S[j] = S[j], S[i]
    out = bytearray(); i = j = 0
    for c in data:
        i = (i + 1) & 0xFF; j = (j + S[i]) & 0xFF
        S[i], S[j] = S[j], S[i]
        out.append(c ^ S[(S[i] + S[j]) & 0xFF])
    return bytes(out)

KEY2 = b'p5HjXnu-kCrekIj_bLziI4aW'
def dec_cl2(d):  # RC4
    return rc4(KEY2, d)

def dec_cl3(d):  # обратный xorshift-кейстрим
    x = (0x6A9B701C ^ 0xB037BF34) & 0xFFFFFFFF
    out = bytearray(d)
    for i in range(len(out)):
        x = (x ^ (x << 13)) & 0xFFFFFFFF
        x = (x ^ (x >> 17)) & 0xFFFFFFFF
        x = (x ^ (x << 5))  & 0xFFFFFFFF
        out[i] ^= x & 0xFF
    return bytes(out)

DEC = {0: dec_cl0, 1: dec_cl1, 2: dec_cl2, 3: dec_cl3}
```

Проверка CRC и сборка:

```python
recovered = {}
i = 0
while True:
    i = mm.find(b'DATX', i)
    if i < 0: break
    if i + 20 <= len(mm):
        magic, idx, cid, ch, ln, crc = struct.unpack('<IIHHII', mm[i:i+20])
        if ln and 1 <= ln <= 128 and idx < 8 and cid < 4 and ch < 3:
            data  = mm[i+20:i+20+ln]
            plain = DEC[cid](data)
            if zlib.crc32(plain) == crc and idx not in recovered:
                recovered[idx] = (cid, ln, crc, plain, i)
    i += 1

png = b''.join(recovered[idx][3] for idx in range(8))
open('out/flag.png','wb').write(png)
```

Вывод скрипта:

```
recovered chunks [0, 1, 2, 3, 4, 5, 6, 7]
0 cid 0 len 128 crc 1797098371  from 0x8b66c78
1 cid 1 len 128 crc 3405870171  from 0x8b07c78
2 cid 2 len 128 crc 2549867187  from 0xa8cec78
3 cid 3 len 128 crc 2031548828  from 0xa028c78
4 cid 0 len 128 crc 1684294195  from 0x8b05c78
5 cid 1 len 128 crc 2453593637  from 0x168d1c78
6 cid 2 len 128 crc 2781267344  from 0x633cc78
7 cid 3 len  45 crc 3956758277  from 0xba33c78
total 941
89504e470d0a1a0a0000000d49484452 ... 0000000049454e44ae426082
```

Первые байты — `89 50 4E 47 0D 0A 1A 0A` (PNG-сигнатура), последние — `IEND` + CRC. Файл восстановлен.

---

## 9. Верификация и декодирование QR

Проверка целостности PNG (все CRC чанков):

```bash
python3 - <<'PY'
import struct, zlib
d = open('out/flag.png','rb').read()
assert d[:8] == b'\x89PNG\r\n\x1a\n'
p = 8
while p < len(d):
    ln  = struct.unpack('>I', d[p:p+4])[0]
    typ = d[p+4:p+8]; data = d[p+8:p+8+ln]
    crc = struct.unpack('>I', d[p+8+ln:p+12+ln])[0]
    print(typ.decode(), ln, 'crc_ok', (zlib.crc32(typ+data) & 0xFFFFFFFF) == crc)
    p += 12 + ln
PY
```

```
IHDR 13 crc_ok True
IDAT 884 crc_ok True
IEND 0 crc_ok True
```

Тип файла и декодирование QR:

```bash
file out/flag.png
# out/flag.png: PNG image data, 343 x 343, 1-bit grayscale, non-interlaced

zbarimg --raw out/flag.png
# ctfcup{4lpc_r3mn4nts_0f_th3_br0k3r_7hru_p1x3l5}
```

Увеличенная копия для наглядности:

```bash
python3 -c "from PIL import Image; im=Image.open('out/flag.png').convert('L'); im.resize((1372,1372), Image.NEAREST).save('out/flag_big.png')"
```

Хеши/итог:

```
artifacts/recovered_flag.png   941 bytes, PNG 343x343 (1-bit), QR -> ctfcup{...}
```

---

## 10. Почему решение вообще возможно (сводка «дырок» в защите)

1. **Файл только читали.** `cl*.exe` открывают `flag.png` с `GENERIC_READ`; ни один процесс в него не пишет. «Шифрование» существует лишь в IPC-трафике и памяти.
2. **CRC32 открытого текста не проверялся.** Клиенты кладут CRC исходного чанка в `DATX`, а broker его игнорирует. Это дало нам «оракул» для проверки расшифровки и для брутфорса ключа `cl2`.
3. **Преобразования обратимы и без секретов:** XOR с константой, ROR+ADD, xorshift с константным seed, RC4 с ключом из `cl2.exe`. Никакой связи с раундами/сессией нет.
4. **8 раундов ничего не дают**, т.к. каждый раунд читает неизменённый файл — все `DATX` идентичны.
5. **`purge.exe` не спас** содержимое: он чистит standby list (файловый кэш), но `DATX`-буферы — это куча/ALPC, они остались в физической памяти. К тому же образы/скрипты остались как `FILE`-объекты.
6. **Удаление файла** (`RNGCryptoServiceProvider` + `Remove-Item`) уничтожило только дисковую копию — данные уже были «украдены» в RAM.

---

## 11. Воспроизведение (шпаргалка команд)

```bash
cd /root/dev/ctfcup-2026/puzzle
VOL=~/tools/volatility3/vol.py
DUMP=Puzzle_CTFCUP-Snapshot7.vmem

# 1. триаж
python3 $VOL -f $DUMP windows.info
python3 $VOL -f $DUMP windows.pstree  > work/pstree.txt
python3 $VOL -f $DUMP windows.cmdline > work/cmdline.txt

# 2. файлы из памяти
python3 $VOL -f $DUMP windows.filescan > work/filescan.txt
grep -i "vm-run" work/filescan.txt
mkdir -p work/files
for a in 0x8004920d4b10 0x8004923373e0 0x800492337a20 0x8004924281b0 \
         0x800492432d90 0x800492434690 0x800492437a20 0x800492438ce0 0x800492438e70; do
  python3 $VOL -f $DUMP -o work/files windows.dumpfiles --virtaddr $a
done

# 3. реверс (IDA-MCP или objdump) — см. §5–§6

# 4. сборка флага (скрипт из Приложения A)
python3 solve.py

# 5. проверка
zbarimg --raw out/flag.png
```

---

## Приложение A. Полный `solve.py`

```python
#!/usr/bin/env python3
"""
CTFCup 2026 Puzzle: восстановление flag.png из дампа памяти.

Идея:
  broker.exe разбивает файл на чанки по 128 байт и распределяет их
  round-robin по 4 клиентам (chunk & 3). Каждый клиент читает свой чанк
  (только чтение), преобразует его своим обратимым алгоритмом и отправляет
  DATX-сообщение:
      'DATX' | chunk_idx(u32) | cid(u16) | channel(u16) | len(u32) | crc32(plaintext) | data[len]
  Восстановив 4 алгоритма (реверс client-бинарников) и найдя DATX в дампе,
  расшифровываем чанки, проверяем CRC32 и склеиваем PNG.
"""
import mmap, struct, zlib, sys

def ror8(v, n): return ((v >> n) | (v << (8 - n))) & 0xFF
def rol8(v, n): return ((v << n) | (v >> (8 - n))) & 0xFF

# ---- cl0: XOR с 16-байтным ключом -------------------------------------
# байты по RVA 0xF328 (32 шт): key[i] = b[i] ^ b[i+16]
KEY0 = bytes.fromhex('ea8e2bbc5e2ec467bc6268b0de893f6d')
def dec_cl0(d):
    return bytes(d[i] ^ KEY0[i % 16] for i in range(len(d)))

# ---- cl1: ROR8(b,5) + 0x5A --------------------------------------------
def dec_cl1(d):
    return bytes(rol8((x - 0x5A) & 0xFF, 5) for x in d)

# ---- cl2: RC4, ключ 24 байта из образа ---------------------------------
KEY2 = b'p5HjXnu-kCrekIj_bLziI4aW'
def rc4(key, data):
    S = list(range(256)); j = 0
    for i in range(256):
        j = (j + S[i] + key[i % len(key)]) & 0xFF
        S[i], S[j] = S[j], S[i]
    out = bytearray(); i = j = 0
    for c in data:
        i = (i + 1) & 0xFF
        j = (j + S[i]) & 0xFF
        S[i], S[j] = S[j], S[i]
        out.append(c ^ S[(S[i] + S[j]) & 0xFF])
    return bytes(out)
def dec_cl2(d):
    return rc4(KEY2, d)

# ---- cl3: xorshift32 keystream, seed = 0x6A9B701C ^ 0xB037BF34 --------
def dec_cl3(d):
    x = (0x6A9B701C ^ 0xB037BF34) & 0xFFFFFFFF
    out = bytearray(d)
    for i in range(len(out)):
        x = (x ^ (x << 13)) & 0xFFFFFFFF
        x = (x ^ (x >> 17)) & 0xFFFFFFFF
        x = (x ^ (x << 5)) & 0xFFFFFFFF
        out[i] ^= x & 0xFF
    return bytes(out)

DEC = {0: dec_cl0, 1: dec_cl1, 2: dec_cl2, 3: dec_cl3}

def main(path='Puzzle_CTFCUP-Snapshot7.vmem', out='out/flag.png'):
    f = open(path, 'rb')
    mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)

    # --- CTRL: узнаём раскладку чанков и размер файла ---
    ctrl = {}
    i = 0
    while True:
        i = mm.find(b'CTLX', i)
        if i < 0: break
        if i + 32 <= len(mm):
            magic, typ, idx, off, ln, cid, ch, extra = struct.unpack('<IIIIIHHQ', mm[i:i+32])
            if typ == 1 and ln and 1 <= ln <= 128 and idx < 4096:
                ctrl.setdefault(idx, (off, ln, cid, ch))
        i += 1
    if ctrl:
        last_off, last_len = ctrl[max(ctrl)][0], ctrl[max(ctrl)][1]
        print(f'[i] чанков по CTRL: {len(ctrl)}, размер файла: {last_off + last_len}')

    # --- DATX: расшифровываем и проверяем CRC ---
    recovered = {}
    i = 0
    while True:
        i = mm.find(b'DATX', i)
        if i < 0: break
        if i + 20 <= len(mm):
            magic, idx, cid, ch, ln, crc = struct.unpack('<IIHHII', mm[i:i+20])
            if ln and 1 <= ln <= 128 and idx < 4096 and cid < 4 and ch < 3:
                data = mm[i+20:i+20+ln]
                try:
                    plain = DEC[cid](data)
                except Exception:
                    i += 1; continue
                if zlib.crc32(plain) == crc and idx not in recovered:
                    recovered[idx] = (cid, ln, crc, plain, i)
        i += 1

    print('[i] восстановлено чанков:', sorted(recovered))
    if not recovered:
        sys.exit('[-] DATX не найдены')
    total = max(recovered) + 1
    if len(recovered) != total:
        sys.exit(f'[-] не хватает чанков: есть {sorted(recovered)}, ожидалось {total}')

    png = b''.join(recovered[idx][3] for idx in range(total))
    open(out, 'wb').write(png)
    print(f'[+] {out}: {len(png)} байт, header={png[:8].hex()}')
    for idx in range(total):
        cid, ln, crc, plain, off = recovered[idx]
        print(f'    chunk {idx}: cid={cid} len={ln} crc={crc} @0x{off:x}')

if __name__ == '__main__':
    main(*sys.argv[1:])
```

## Приложение B. Брутфорс ключа `cl2` (`/tmp/brutekey.c`)

```c
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>

static uint32_t crc32_(const uint8_t *d, size_t n) {
    uint32_t c = 0xffffffffu;
    for (size_t i = 0; i < n; i++) {
        c ^= d[i];
        for (int k = 0; k < 8; k++)
            c = (c >> 1) ^ (0xEDB88320u & (0u - (c & 1u)));
    }
    return ~c;
}

int main(int argc, char **argv) {
    // argv[1] = образ cl2, argv[2] = 128-байтный ciphertext, argv[3] = ожидаемый CRC32
    FILE *f = fopen(argv[1], "rb");
    fseek(f, 0, SEEK_END); long n = ftell(f); fseek(f, 0, SEEK_SET);
    uint8_t *d = malloc(n); if (fread(d, 1, n, f) != (size_t)n) return 1;
    fclose(f);

    uint8_t ct[256];
    FILE *g = fopen(argv[2], "rb");
    int ctl = (int)fread(ct, 1, 128, g);
    fclose(g);
    uint32_t want = (uint32_t)strtoul(argv[3], 0, 10);

    int deltas[] = {0x10, 0x18, 0x20, 0x24, 0x28, 0x30, 0x38, 0x40};
    for (int di = 0; di < 8; di++) {
        int dl = deltas[di];
        for (long o = 0; o + dl + 24 < n; o++) {
            uint8_t key[24];
            for (int i = 0; i < 24; i++) key[i] = d[o + i] ^ d[o + dl + i];

            uint8_t S[256];
            for (int i = 0; i < 256; i++) S[i] = (uint8_t)i;
            int j = 0;
            for (int i = 0; i < 256; i++) {
                j = (j + S[i] + key[i % 24]) & 0xff;
                uint8_t t = S[i]; S[i] = S[j]; S[j] = t;
            }
            uint8_t out[128]; int a = 0, b = 0;
            for (int k = 0; k < ctl; k++) {
                a = (a + 1) & 0xff;
                b = (b + S[a]) & 0xff;
                uint8_t t = S[a]; S[a] = S[b]; S[b] = t;
                out[k] = ct[k] ^ S[(S[a] + S[b]) & 0xff];
            }
            if (crc32_(out, (size_t)ctl) == want) {
                printf("FOUND o=%ld delta=%d key=", o, dl);
                for (int i = 0; i < 24; i++) printf("%02x", key[i]);
                printf("  (\"");
                for (int i = 0; i < 24; i++) putchar(key[i]);
                printf("\")\n");
            }
        }
    }
    return 0;
}
```

Сборка и запуск:

```bash
gcc -O2 -o /tmp/brutekey /tmp/brutekey.c
/tmp/brutekey $(ls work/files/file.0x800492438ce0*) /tmp/ct2.bin 2549867187
```

```
FOUND o=58664 delta=24 key=7035486a586e752d6b4372656b496a5f624c7a6949346157  ("p5HjXnu-kCrekIj_bLziI4aW")
```

---

## Приложение C. Артефакты в репозитории

```
Puzzle_CTFCUP-Snapshot7.vmem        исходный дамп (2 GiB)
WRITEUP.md                          этот отчёт
out/flag.png                        восстановленный PNG (941 байт)
out/flag_big.png                    он же x4 (для наглядности)
artifacts/recovered_flag.png        копия флага
artifacts/broker.exe                broker.exe, извлечён из памяти
artifacts/cl0.exe, cl1.exe, cl3.exe клиенты, извлечены из памяти
artifacts/purge.exe                 purge.exe, извлечён из памяти
artifacts/...RUN.ps1.dat            дамп секции RUN.ps1 (нули; текст восстановлен из сырого дампа)
artifacts/...orchestrate.ps1.dat    оригинальный orchestrate.ps1
work/files/                         первичные дампы FILE-объектов (в т.ч. образ cl2)
```

---

## Итог

Флаг:

```
ctfcup{4lpc_r3mn4nts_0f_th3_br0k3r_7hru_p1x3l5}
```

Ключевая мысль таска: «безопасное удаление» файла бесполезно, если до удаления его содержимое разошлось по IPC-сообщениям других процессов. Плюс «шифрование» оказалось набором обратимых преобразований без ключа, а «раунды» не меняли данные, потому что файл открывался только на чтение — поэтому единственный настоящий секрет (QR-картинка) полностью восстанавливался из `DATX`-буферов в RAM.
