# Mobile Treasure Hunters | forensics, mobile, reverse

**Автор:** [@sib_coder](https://t.me/sib_coder) · [GitHub](https://github.com/Sib-Coder)

## Описание

> Изъят телефон курьера. Переписка велась в мессенджере Burnt Note, где
> сообщения самоуничтожаются после прочтения. После тотальной чистки таблица
> сообщений пуста, а синхронизация с сервером `sync.burntnote.onion` недоступна.
>
> Восстановите последнее сообщение переписки и найдите в нём контрольную фразу.

## Деплой

Не требуется.

## Выдать участникам

- [evidence.tar.gz](evidence.tar.gz)
- [burntnote.apk](burntnote.apk)

```text
handout/evidence.tar.gz  — forensic-образ с артефактами устройства
handout/burntnote.apk    — APK Burnt Note для реверса
```

В архиве находятся:

```text
/data/data/com.ctf.burntnote/databases/messages.db
/data/data/com.ctf.burntnote/databases/messages.db-wal
/data/data/com.ctf.burntnote/shared_prefs/burnt_settings.xml
/data/data/com.ctf.burntnote/files/diagnostics.log
/data/data/com.ctf.burntnote/files/release.lock
/data/data/com.android.chrome/app_chrome/Default/History
/data/data/com.android.providers.contacts/databases/contacts2.db
/data/data/com.whatsapp/databases/msgstore.db
/data/misc/wifi/WifiConfigStore.xml
/data/secure/0/settings_secure.xml
/data/tombstones/tombstone_00
/sdcard/DCIM/Camera/IMG_20260113_192401.jpg
```

`release.lock`, контакты, Wi-Fi, Chrome-история и tombstone создают шум.
APK нужен для восстановления форматов seed и криптографических параметров;
запускать его бессмысленно — сервер мёртв.

## Идея

Оффлайн-таск по мобильной форензике и реверсу Android-приложения.

Участнику выдаются forensic-образ телефона и APK мессенджера **Burnt Note**.
Сервер, эмулятор и рабочее приложение не нужны: всё необходимое находится в
артефактах устройства и исходных форматах, которые нужно восстановить по APK.

Цель — восстановить последнее сообщение самоуничтожающейся переписки и найти
в нём флаг.

Таск построен вокруг восстановления удалённых данных из нескольких слоёв
Android-устройства:

- seed собирается из четырёх артефактов с разными форматами времени;
- строки сообщений распределены между основной SQLite-базой, freelist,
  freeblock-остатками и WAL;
- ключ каждого сообщения зависит от полного plaintext предыдущего сообщения.

Обычный SQLite показывает только часть данных и после WAL-replay приходит к
финальному пустому состоянию. Поэтому историю нужно карвить вручную, а затем
проверять физические образы расшифровкой AES-256-GCM.

## Решение

### 1. Собрать seed

Найти четыре 12-символьных hex-фрагмента:

| Источник | Артефакт | Временная метка |
| --- | --- | --- |
| EXIF `UserComment` | `IMG_20260113_192401.jpg` | `DateTimeOriginal` + `OffsetTime` |
| Chrome URL | `History`, `visits.visit_time` | WebKit, микросекунды с 1601-01-01 |
| WhatsApp-код | `msgstore.db`, `messages.timestamp` | Unix-секунды |
| recovery-фрагмент | `diagnostics.log`, префикс `[...]` | Unix-миллисекунды |

Привести все метки к UTC, отсортировать фрагменты по времени и склеить их через
`-`. Для текущей выдачи порядок такой:

```text
WhatsApp (16:02:11Z)
Фото (16:24:01Z)
diagnostics.log (16:31:02.011Z)
Chrome (16:45:33Z)
```

Для Chrome:

```text
utc_ms = visit_time / 1000 - 11644473600000
```

Затем найти `ANDROID_ID` в `settings_secure.xml` и получить master key:

```text
seed_string = "<frag1>-<frag2>-<frag3>-<frag4>"
salt        = Settings.Secure.ANDROID_ID
master      = PBKDF2-HMAC-SHA256(seed_string, salt, 100000, 32)
```

### 2. Восстановить сообщения

Схема таблицы:

```sql
CREATE TABLE messages(
  id INTEGER PRIMARY KEY,
  created_at INTEGER NOT NULL,
  sender TEXT NOT NULL,
  nonce BLOB NOT NULL,
  frame BLOB NOT NULL
);
```

Нужно собрать 12 строк из всех физических источников:

- сообщения 1, 3, 5, 6 и 7 видны в основной базе;
- сообщения 2 и 4 находятся в freeblock-остатках и удалённых ячейках;
- freelist содержит удалённую таблицу `drafts` и шум;
- сообщения 8–12 находятся в ранних кадрах WAL до финального `DELETE`.

Первые 8 байт WAL обнулены, поэтому стандартный SQLite игнорирует WAL. Его
нужно разобрать вручную: 32-байтный заголовок, затем 24-байтные заголовки
кадров и страницы. Для поиска строк полезна сигнатура serial types:

```text
00 05 0f 24 96 1c
```

Дубликаты и повреждённые образы проверяются несовпадением GCM-тега.

### 3. Расшифровать цепочку

```text
key_1 = HMAC-SHA256(master, "burnt-note/root")
key_i = HMAC-SHA256(key_{i-1}, padded_plain_{i-1} + "|burnt-note/step|" + i)

padded_plain_i = UTF-8(text_i), zero-padded до 1400 байт
aad_i          = "burnt-note/msg/" + i
frame_i        = AES-256-GCM(key_i, nonce_i, aad_i, padded_plain_i)
```

`frame_i` содержит `ciphertext || tag`. Открывать сообщения нужно строго по
порядку: ключ сообщения 12 зависит от полного 1400-байтного plaintext
сообщения 11, включая нулевой padding.

```text
k1 <- HMAC(master, "burnt-note/root")
p1 <- GCM-open(k1, row1)
k2 <- HMAC(k1, p1 || "|burnt-note/step|2")
p2 <- GCM-open(k2, row2)
...
```

## Подсказки

Выдавать по одной:

1. Таблица не врёт о себе, но база помнит больше: посмотрите сырые страницы и freelist.
2. У WAL стерта сигнатура. Его формат документирован, а replay покажет только финальное состояние.
3. Четыре артефакта используют четыре формата времени. Сначала приведите их к UTC.
4. Ключ каждого сообщения зависит от plaintext предыдущего. Padding до 1400 байт тоже входит в plaintext.

## Сборка и проверка

Из корня `burnt-note`:

```sh
cd tools
python3 build_evidence.py
python3 check_parity.py
cd ..
python3 solve/solve.py handout/evidence.tar.gz
```

Сборка APK:

```sh
cd android
./build_apk.sh
```

Для публикации используется R8. Полный release pipeline:

```sh
R8_VERSION=9.5.26 tools/build_release.sh
```

Авторский solver использует Python stdlib и Pillow для чтения EXIF; AES-256-GCM
реализован локально в `tools/aesgcm.py`.

## Флаг

```text
ctfcup{ch41n_0f_4sh3s}
```
