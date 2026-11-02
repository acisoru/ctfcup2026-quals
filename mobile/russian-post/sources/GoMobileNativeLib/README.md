# GoMobileNativeLib

GoMobile-библиотека для `sealed-prefs`.

В Android она подключается как `mobilelib.aar` и экспортирует Java-класс
`mobilelib.Mobilelib`.

## Что Вынесено В Native

- `isRootedEnvironment(fingerprint, model, product, tags)`
- `verifySealedParcel(parcelB64, ivB64, keyB64)`
- `fF1..fF12` возвращают только decoy-строки в формате флага

Настоящий plaintext-флаг в native-библиотеке не хранится. Он остается на backend
и попадает к игроку только как encrypted parcel.

## Проверки

```sh
go test ./...
```

## Сборка AAR

```sh
gomobile bind -target=android -androidapi=23 -trimpath -ldflags='-s -w' -o mobilelib.aar .
```

Для локальной сборки нужны `gomobile`, `gobind`, Android SDK и Android NDK.

## Интеграция С APK

`android/build_apk.sh` по умолчанию берет:

```text
GoMobileNativeLib/mobilelib.aar
```

Скрипт проверяет, что AAR содержит методы:

```text
isRootedEnvironment(String, String, String, String)
verifySealedParcel(String, String, String)
```

Если AAR отсутствует или устарел, сборка APK остановится с ошибкой.

## Что Не Коммитить

Эти файлы генерируются локально и игнорируются:

```text
mobilelib.aar
mobilelib-sources.jar
mylib_unpacked/
```

Перед публикацией handout пересоберите AAR, затем APK, и обновите
`sealed-prefs.apk` в корне таска.
