# Peridromofilia | web

**Автор:** [@arseny2606](https://t.me/arseny2606)

## Описание

> «Их метро» - клуб коллекционеров транспортных карт «Тройка» - перевёл
> членскую базу в сеть. Заведите карту участника, ведите журнал поездок,
> отмечайте тройки в коллекции и обменивайтесь картами.

## Деплой

Per-instance: [deploy/](deploy/).

## Выдать участникам

Ничего.

## Идея

Плоский сайт клуба на Flask + mongoengine. Профиль участника - embedded-документ
`Profile` с `allow_inheritance=True`, поэтому в базе у него лежит служебное поле
`_cls`. Эндпоинт `PATCH /api/profile` тело запроса полностью уносит в
`QuerySet.update()`: известные ключи (`nickname`, `home_station`) проходят через
словарь алиасов, всё остальное (в том числе `set__*` и `__raw__`) уходит в апдейт
как есть - классический mass assignment.

Прямая подмена класса валидацию не проходит: `EmbeddedDocumentField` проверяет
isinstance и пускает только подклассы `Profile`. Обход - документированный
escape hatch mongoengine `__raw__`, пишущий сырой SON в MongoDB мимо модели.
При чтении `EmbeddedDocumentField.to_python` резолвит `_cls` через глобальный
`_DocumentRegistry` без проверки иерархии, поэтому embedded-поле можно
подменить на любой зарегистрированный в процессе класс. Для top-level
документов queryset добавляет фильтр `_cls IN <иерархия>` и документ с чужим
`_cls` перестаёт находиться - окно существует только в embedded-поле.

Посторонний класс `ServiceCard` («служебная карта»)
зарегистрирован в том же процессе; его `badge()` читает `/flag.txt` и
возвращает «Служебный доступ: <флаг>», что `/me` и печатает как статус карты.

1. `/members` - техническая колонка «Право участия» светит внутренние коды
   карт: `Profile`, `GoldenProfile`, `ServiceCard` (в клубе есть Вахтер Галина Ивановна - с `ServiceCard`);
2. фингерпринты ошибок на `PATCH /api/profile` выдают mongoengine
   (`FieldDoesNotExist`, `LookUpError`), а работающий синтаксис
   `set__profile__...` показывает, что тело уходит в `QuerySet.update()`;
3. остаётся вспомнить про `_cls` у embedded-документов с наследованием и
   про `__raw__`.

## Решение

`PATCH /api/profile` с `{"__raw__": {"$set": {"profile": {"_cls": "ServiceCard"}}}}`,
затем `GET /me`: статус карты печатает `ServiceCard.badge()` - служебный доступ
с флагом.

Разбор: [solve/WRITEUP.md](solve/WRITEUP.md). Эксплоит:
[solve/exploit.py](solve/exploit.py).

## Флаг

```
ctfcup{g1v3_m3_all_tr0ikas_%s}
```
