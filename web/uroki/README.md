# Электронный журнал | web

**Автор:** [@arseny2606](https://t.me/arseny2606)

## Описание

> Заведите урок, приложите файл - и ждите звонка.

## Деплой

Per-instance: [deploy/](deploy/).

## Выдать участникам

[public/uroki.zip](public/uroki.zip)

## Идея

Уязвимая цепочка из трёх шагов:

1. загрузка вложения идёт через `app/storage.py`: `clean_name()` блокирует
   `..` и обратные слэши, но не абсолютные пути - `os.path.join(UPLOAD_DIR,
   "/data/celerybeat-schedule")` отбрасывает `UPLOAD_DIR`, произвольная запись;
2. beat хранит расписание в стоковом `PersistentScheduler` (класс
   `JournalScheduler`), т.е. через `shelve`, а `shelve` - это `pickle`.
   Файл состояния нигде явно не задаётся: воркер работает с
   `directory=/data`, поэтому используется дефолтное имя
   `celerybeat-schedule` (`/data/celerybeat-schedule`). Файл читается
   стоковым `PersistentScheduler.setup_schedule()` на каждом старте
   воркера;
3. создание урока вызывает `app/ops.py:apply_schedule_changes()` =
   `supervisorctl restart celery`, рестарт = чтение подменённого файла =
   исполнение произвольного кода.

Пока файлы beat живого воркера держат `celerybeat-schedule` открытым, перезапись
портит gdbm; после нескольких рестартов воркер падает в FATAL, файл
освобождается и нагрузка исполняется. Отсюда цикл «переписал -
перезапустил - проверил».

Флаг лежит в `/flag.txt` с режимом `0000` (владелец `app`), это делает
entrypoint - процедуру участники в раздатке не видят.

## Решение

Сборка gdbm-файла с `__reduce__` внутри такого же образа, загрузка его
под абсолютным именем `/data/celerybeat-schedule` к ранее созданному
уроку (обход `clean_name`), создание урока для рестарта
воркера, чтение флага через `chmod` от владельца и эксфильтрация
содержимого через скачивание вложения.

Разбор: [solve/WRITEUP.md](solve/WRITEUP.md). Эксплоит:
[solve/exploit.py](solve/exploit.py).

## Флаг

```
ctfcup{v53_ur0k1_5d3l4ny_5_0gyrc0m_%s}
```
