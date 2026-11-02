# Russian Post: Trust Level | mobile

**Автор:** [@sib_coder](https://t.me/sib_coder) · [GitHub](https://github.com/Sib-Coder)

## Описание

Перед вами идеальное приложение для курьеров: минималистичный интерфейс,
важный виджет с посылкой, строгая проверка курьера и полное ощущение, что
кто-то в продуктовой команде слишком поверил в слово "запечатано".

Курьеру обещали, что внутри приложения все надежно: маршрут выдается только
"своим", секретная посылка выглядит закрытой, а кнопки говорят ровно столько,
сколько должен знать человек на смене. Ваша задача проще и неприятнее для
разработчиков: понять, что именно спрятано в посылке.

## Деплой

Требуется: [sources/docker-compose.yml](sources/docker-compose.yml).

## Выдать участникам

- [sealed-prefs.apk](sealed-prefs.apk)

## Идея

Android CTF-задание уровня Medium.

Игрок получает APK курьерского приложения. Приложение работает с приватными
`SharedPreferences`, HTTPS-бэкендом и локальной проверкой доверия устройства.
Основная идея таска: предварительно пропатчить APK так, чтобы приложение не
обнаруживало root/эмулятор, получить сохраненную сессию из приватных prefs и
использовать ее для запроса ключа.

## Решение

1. Установить APK на эмулятор или rooted-устройство. Приложение обнаружит
   недоверенное окружение и остановит синхронизацию до первого API-запроса.
2. Разобрать APK через jadx/apktool и найти:

- `BuildConfig.API_BASE_URL`
- `MainActivity.isRootedEnvironment()`
- `NativeBridge`
- `mobilelib.Mobilelib`
- `GET /api/config`
- `POST /api/parcel`
- `POST /api/key`
- JSON-поле `"rooted"`
- диагностическую кнопку допуска, почти пустой probe-запрос к `/api/key` и
  метод сборки полного key-request из prefs
- запись `parcel.xml` в приватные `SharedPreferences`
- вызов проверки parcel в `ParcelCipher`
- native-алгоритм проверки формата `parcel-v2`

3. Пропатчить метод так, чтобы он возвращал `false`, собрать и заново подписать
   APK. После патча приложение отправляет серверу `"rooted": false`.
4. Запустить пропатченное приложение. Оно проходит только первую часть
   протокола `parcel-v2`:

```text
GET  /api/config  -> challenge, expires_at, session
POST /api/parcel  -> sealed parcel, IV, receipt
```

После успешного ответа приложение сохраняет в
`/data/data/com.ctf.sealedprefs/shared_prefs/parcel.xml`:

```text
sealed_parcel
iv
challenge
expires_at
session
receipt
package
version
rooted=false
fingerprint
model
android_id
```

Диагностическая кнопка допуска тоже обращается к `POST /api/key`, но отправляет
почти пустой probe-запрос. Ответ содержит только сообщение, что key-сервис жив и
ждет параметры маршрута. Ключ по этому пути не возвращается.

5. Извлечь `parcel.xml` из песочницы приложения. Штатный `run-as` не подходит,
   потому что APK собран с `android:debuggable="false"`. Ожидаемый путь для
   CTF-решения — использовать реальный root-доступ на устройстве или
   userdebug-эмулятор:

```sh
adb shell su -c 'cat /data/data/com.ctf.sealedprefs/shared_prefs/parcel.xml' > parcel.xml
```

На AOSP/userdebug-эмуляторе возможен вариант:

```sh
adb root
adb pull /data/data/com.ctf.sealedprefs/shared_prefs/parcel.xml parcel.xml
```

6. Пока `challenge` не истек, собрать из prefs тот же signed report и запросить
   ключ:

```text
POST /api/key -> session key
```

Сервер проверяет подпись `session`, `rooted=false`, срок жизни challenge и
`receipt`, привязанный к challenge и параметрам устройства из отчета. Ключ и IV
уникальны для каждой сессии.

7. Восстановить алгоритм из `ParcelCipher`/native library и расшифровать
   `sealed_parcel`.
   Авторский `solve/solve.py` принимает извлеченный `parcel.xml`, запрашивает
   `/api/key` и расшифровывает посылку. Участникам solver не выдается.

## Недоверенное Устройство

Если локальная проверка считает устройство недоверенным, приложение не отправляет
запросы к бэкенду и не сохраняет данные сессии. Даже после успешного патча
данные лежат в приватной песочнице, поэтому для извлечения `parcel.xml` нужен
root-доступ или userdebug-эмулятор. Штатный `run-as` недоступен, поскольку APK
собран с `android:debuggable="false"`.

## Вариант Решения Через MITM

MITM не заменяет патч root-check. Сначала участнику все равно нужно заставить
приложение считать устройство доверенным, иначе оно не дойдет до нормального
протокола и не сохранит данные маршрута.

1. Установить APK на эмулятор или rooted-устройство и убедиться, что приложение
   блокируется локальной проверкой.
2. Разобрать APK через jadx/apktool и найти:

- `MainActivity.isRootedEnvironment()`
- native root-check через `mobilelib.Mobilelib`
- certificate pinning через `res/raw/server_cert.pem`
- `GET /api/config`
- `POST /api/parcel`
- `POST /api/key`
- JSON-поле `"rooted"`
- `keyProbeRequest()`
- `keyRequestFromPreferences()`
- `ApiContract.KEY_REQUEST_FIELDS`

3. Пропатчить APK:

- `isRootedEnvironment()` должен возвращать `false`
- certificate pinning нужно отключить или заменить доверенным CA MITM-прокси
- APK нужно пересобрать и заново подписать

4. Настроить Burp Suite, mitmproxy или другой HTTPS-прокси:

- направить трафик эмулятора через прокси
- установить CA-сертификат прокси в систему или использовать патч pinning
- запустить пропатченное приложение

5. Перехватить нормальный протокол:

```text
GET  /api/config  -> challenge, expires_at, session
POST /api/parcel  -> parcel, iv, receipt
POST /api/key     -> probe: сервер жив и ждет signed route parameters
```

6. Собрать полноценный запрос к `/api/key` из перехваченных значений:

```json
{
  "package": "com.ctf.sealedprefs",
  "version": 2,
  "challenge": "...",
  "expires_at": 1234567890,
  "session": "...",
  "rooted": false,
  "fingerprint": "...",
  "model": "...",
  "android_id": "...",
  "receipt": "..."
}
```

7. Ответ `/api/key` на полный корректный report вернет ключ:

```json
{
  "key": "...",
  "algorithm": "parcel-v2"
}
```

8. Восстановить алгоритм из `ParcelCipher`/native library и расшифровать
   посылку:

- `parcel` взять из ответа `/api/parcel`
- `iv` взять из ответа `/api/parcel`
- `key` взять из ответа `/api/key`

В этом варианте MITM удобен для наблюдения `challenge`, `session`, `receipt`,
`parcel` и `iv`. Но решающий шаг остается тем же: пропатчить локальную проверку,
повторить key-request с полными параметрами и расшифровать `parcel-v2`.

## Флаг

```
ctfcup{p4rcel_v1_unl0ck3d}
```
