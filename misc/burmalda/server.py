#!/usr/bin/env python3
"""Small static web server for a Godot 4 web export.

Features:
  * sends the COOP/COEP headers required for cross-origin isolation
    (SharedArrayBuffer / threading) plus the correct `application/wasm` MIME type;
  * serves pre-compressed `.gz` siblings when the client accepts gzip;
  * supports single-range requests (used by streaming WASM compilation).

It has no third-party dependencies. `--precompress <dir>` regenerates the
`.gz` siblings at image build time.
"""

from __future__ import annotations

import argparse
import gzip
import os
import shutil
import sys
from email.utils import formatdate
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".htm": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".wasm": "application/wasm",
    ".pck": "application/octet-stream",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".txt": "text/plain; charset=utf-8",
    ".map": "application/json; charset=utf-8",
}

COMPRESSIBLE = {".html", ".htm", ".js", ".mjs", ".css", ".json", ".wasm", ".pck", ".svg", ".txt", ".map"}

GAME_DIR = Path(os.environ.get("GAME_DIR", "/app/game")).resolve()
INDEX_FILES = [name for name in os.environ.get("INDEX_FILE", "index.html").split(",") if name]
CACHE_MAX_AGE = int(os.environ.get("CACHE_MAX_AGE", "3600"))

COOP = os.environ.get("COOP", "same-origin")
COEP = os.environ.get("COEP", "require-corp")
CORP = os.environ.get("CORP", "same-origin")


def precompress(root: Path, min_size: int = 1024) -> None:
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in COMPRESSIBLE:
            continue
        target = Path(str(path) + ".gz")
        if target.exists() and target.stat().st_mtime >= path.stat().st_mtime:
            continue
        if path.stat().st_size < min_size:
            continue
        with open(path, "rb") as src, gzip.GzipFile(str(target), "wb", compresslevel=6, mtime=0) as dst:
            shutil.copyfileobj(src, dst, length=1 << 20)
        print(f"precompressed {path} -> {target}", flush=True)


def parse_range(header: str, size: int) -> tuple[int, int] | None:
    if not header.startswith("bytes="):
        return None
    spec = header[len("bytes="):].split(",", 1)[0].strip()
    if "-" not in spec:
        return None
    start_s, end_s = spec.split("-", 1)
    try:
        if start_s == "":
            length = int(end_s)
            if length <= 0:
                return None
            start = max(0, size - length)
            end = size - 1
        else:
            start = int(start_s)
            end = int(end_s) if end_s else size - 1
    except ValueError:
        return None
    if start < 0 or start >= size or end < start:
        return None
    return start, min(end, size - 1)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "BurmaldaStatic/1.0"

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def do_HEAD(self) -> None:
        self._serve(head_only=True)

    def do_GET(self) -> None:
        self._serve(head_only=False)

    def _serve(self, head_only: bool) -> None:
        path = urlsplit(self.path).path

        fs_path = self._resolve(path)
        if fs_path is None:
            self._error(404, "Not Found")
            return

        try:
            stat = fs_path.stat()
        except OSError:
            self._error(404, "Not Found")
            return

        range_header = self.headers.get("Range")
        accepts_gzip = "gzip" in self.headers.get("Accept-Encoding", "").lower()
        gz_path = Path(str(fs_path) + ".gz")

        # Range responses must be on the identity representation.
        use_gzip = accepts_gzip and range_header is None and gz_path.exists()
        send_path = gz_path if use_gzip else fs_path

        try:
            total = send_path.stat().st_size
        except OSError:
            self._error(404, "Not Found")
            return

        content_type = MIME_TYPES.get(fs_path.suffix.lower(), "application/octet-stream")
        is_document = fs_path.suffix.lower() in {".html", ".htm"}
        cache_control = "no-cache" if is_document else f"public, max-age={CACHE_MAX_AGE}"

        start, end = 0, total - 1
        status = 200
        if range_header is not None:
            parsed = parse_range(range_header, total)
            if parsed is None:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{total}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            start, end = parsed
            status = 206

        length = end - start + 1

        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", cache_control)
        self.send_header("Last-Modified", formatdate(stat.st_mtime, usegmt=True))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cross-Origin-Opener-Policy", COOP)
        self.send_header("Cross-Origin-Embedder-Policy", COEP)
        self.send_header("Cross-Origin-Resource-Policy", CORP)
        if use_gzip:
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Vary", "Accept-Encoding")
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{total}")
        self.end_headers()

        if head_only:
            return

        with open(send_path, "rb") as fh:
            fh.seek(start)
            remaining = length
            while remaining > 0:
                chunk = fh.read(min(1 << 20, remaining))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    return
                remaining -= len(chunk)

    def _resolve(self, url_path: str) -> Path | None:
        decoded = unquote(url_path)
        parts = [p for p in decoded.split("/") if p not in ("", ".")]
        if any(p == ".." for p in parts):
            return None

        candidate = GAME_DIR.joinpath(*parts).resolve()
        if candidate != GAME_DIR and GAME_DIR not in candidate.parents:
            return None

        if candidate.is_dir():
            for index in INDEX_FILES:
                indexed = candidate / index
                if indexed.is_file():
                    return indexed
            return None

        return candidate if candidate.is_file() else None

    def _error(self, code: int, message: str) -> None:
        body = f"{code} {message}\n".encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--precompress", metavar="DIR", help="generate .gz siblings under DIR and exit")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    parser.add_argument("--host", default=os.environ.get("HOST", "0.0.0.0"))
    args = parser.parse_args()

    if args.precompress:
        root = Path(args.precompress).resolve()
        precompress(root)
        return 0

    if not GAME_DIR.is_dir():
        print(f"game directory not found: {GAME_DIR}", file=sys.stderr)
        return 1

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    httpd.daemon_threads = True
    print(f"serving {GAME_DIR} on http://{args.host}:{args.port}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
