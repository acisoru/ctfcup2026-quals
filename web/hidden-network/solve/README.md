# Hide network — решение

## Быстрый запуск

Поднять стенд с EPC (нужен `/dev/net/tun`) можно так:

```bash
cd femtocell_web/deploy
FEMTO_WEB_PORT=58080 docker compose --profile epc-lab up --detach --no-build
python3 solve.py --base-url http://127.0.0.1:58080
```

Ожидаемый результат — единственная строка с `ctfcup{...}`. После проверки:

```bash
docker compose --profile epc-lab down --remove-orphans
```

`solve.py` использует только публичный HTTP-порт фемтосоты. Он не обращается к
Docker API, файлам EPC или опубликованному S1-порту: такого порта у стенда нет.

## Цепочка

1. Dashboard содержит legacy connectivity check. Он пропускает строку, если
   она начинается с `http://mme-monitor`, но затем разбирает URL штатным
   парсером. URL
   `http://mme-monitor@femto-agent:8081/v1/jobs/8427` проходит prefix check,
   а реальное HTTP-соединение идёт к `femto-agent` — это user-info часть URL.
2. Внутренний агент не проверяет принадлежность job. IDOR на job `8427`
   возвращает одноразовый `maintenance_ticket`, имя файла диагностики и
   `m_tmsi` обслуживаемого абонента.
3. Ticket открывает `/maintenance/console`. Это shell внутри контейнера
   `femto`, не shell хоста и не shell EPC.
4. Из этого контейнера доступна приватная сервисная сеть, поэтому команда
   `curl http://mme-log-relay:8082/v1/diagnostics/ran-support-cache.log`
   читает отфильтрованный diagnostic cache.
5. В cache выбирается именно запись `S1AP UL NAS trace`, у которой `m_tmsi`
   совпадает со значением из support job. Её `nas_pdu_hex` — защищённый
   исходный TAU PDU, который надо передать без изменений.
6. В образе фемтосоты есть `pysctp` и `pycrate`, но нет готового eNB/replay
   helper. `solve.py` загружает свой `replay.py` в `/tmp` через консоль,
   дробя base64 на команды короче 512 символов, и запускает его там.
7. `replay.py` читает опубликованные параметры S1 из
   `/etc/femto/connections.ini`, создаёт свежую SCTP association с внутренним
   MME, отправляет S1 Setup, затем Initial UE Message с S-TMSI и точным
   захваченным NAS PDU. MME привязывает прежний контекст к новой association
   и возвращает лабораторный маркер с флагом.

Ki, OPc, KASME, счётчики NAS и реализация NAS security для этого не нужны:
PDU уже защищён исходным UE, а задача проверяет ошибочную повторную привязку
контекста MME к другой S1/SCTP association.

## Состав эксплойта

- `solve.py` — HTTP-цепочка: SSRF → IDOR → ticket → console → cache → upload
  и запуск replayer.
- `replay.py` — минимальный SCTP/S1AP клиент, который запускается уже из
  скомпрометированной фемтосоты. Он не импортирует код задания, eNB emulator
  или NAS helper.

Оба файла намеренно используют параметры из ответа/конфига, а не фиксированный
NAS blob или флаг. При следующем запуске EPC solver заново получает актуальные
M-TMSI и TAU PDU из предусмотренной цепочки.
