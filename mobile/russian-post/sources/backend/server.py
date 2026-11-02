#!/usr/bin/env python3
import base64
import hashlib
import hmac
import os
import secrets
import time

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel


FLAG = os.environ.get("FLAG", "ctfcup{p4rcel_v1_unl0ck3d}")
MASTER_KEY = base64.b64decode(os.environ.get("TASK_KEY_B64", "MDEyMzQ1Njc4OWFiY2RlZg=="))
SESSION_SECRET = os.environ.get(
    "TASK_SESSION_SECRET", "sealed-prefs-development-session-secret"
).encode()
CHALLENGE_TTL_SECONDS = int(os.environ.get("CHALLENGE_TTL_SECONDS", "900"))
PACKAGE_NAME = "com.ctf.sealedprefs"

app = FastAPI(title="Sealed Preferences", version="2.0")


class ClientReport(BaseModel):
    package: str
    version: int
    challenge: str
    expires_at: int
    session: str
    rooted: bool | None = None
    fingerprint: str | None = None
    model: str | None = None
    android_id: str | None = None
    receipt: str | None = None


class KeyRequest(BaseModel):
    package: str | None = None
    version: int | None = None
    challenge: str | None = None
    expires_at: int | None = None
    session: str | None = None
    rooted: bool | None = None
    fingerprint: str | None = None
    model: str | None = None
    android_id: str | None = None
    receipt: str | None = None


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def sign(label: str, value: str) -> str:
    message = f"{label}\n{value}".encode()
    return b64url(hmac.new(SESSION_SECRET, message, hashlib.sha256).digest())


def session_signature(challenge: str, expires_at: int) -> str:
    return sign("session-v2", f"{challenge}\n{expires_at}")


def client_identity(report: ClientReport) -> str:
    fields = (
        report.package,
        str(report.version),
        report.challenge,
        str(report.expires_at),
        report.fingerprint or "",
        report.model or "",
        report.android_id or "",
    )
    return "\n".join(fields)


def receipt_for(report: ClientReport) -> str:
    return sign("receipt-v2", client_identity(report))


def derive_material(challenge: str, label: bytes) -> bytes:
    message = label + b"\x00" + challenge.encode()
    return hmac.new(MASTER_KEY, message, hashlib.sha256).digest()[:16]


def parcel_key(challenge: str) -> bytes:
    return derive_material(challenge, b"parcel-key-v2")


def parcel_iv(challenge: str) -> bytes:
    return derive_material(challenge, b"parcel-iv-v2")


def pkcs7_pad(data: bytes, block_size: int = 16) -> bytes:
    pad_len = block_size - (len(data) % block_size)
    return data + bytes([pad_len]) * pad_len


def xor_block(left: bytes, right: bytes) -> bytes:
    return bytes(a ^ b for a, b in zip(left, right))


def toy_aes_cbc_encrypt_for_ctf(plaintext: bytes, key: bytes, iv: bytes) -> bytes:
    # Intentionally not real AES: reversing this routine is part of the task.
    out = bytearray()
    previous = iv
    padded = pkcs7_pad(plaintext)
    for offset in range(0, len(padded), 16):
        block = xor_block(padded[offset : offset + 16], previous)
        encrypted = xor_block(block, key)
        out.extend(encrypted)
        previous = encrypted
    return bytes(out)


def sealed_parcel(challenge: str) -> str:
    encrypted = toy_aes_cbc_encrypt_for_ctf(
        FLAG.encode(), parcel_key(challenge), parcel_iv(challenge)
    )
    return base64.b64encode(encrypted).decode()


def client_error(error: str) -> JSONResponse:
    return JSONResponse(status_code=403, content={"error": error})


def missing_key_fields(report: KeyRequest) -> list[str]:
    missing = []
    for field in ("package", "version", "challenge", "expires_at", "session", "receipt"):
        value = getattr(report, field)
        if value is None or value == "" or field == "expires_at" and value <= 0:
            missing.append(field)
    return missing


def key_report(report: KeyRequest) -> ClientReport:
    return ClientReport(
        package=report.package or "",
        version=report.version or 0,
        challenge=report.challenge or "",
        expires_at=report.expires_at or 0,
        session=report.session or "",
        rooted=report.rooted,
        fingerprint=report.fingerprint,
        model=report.model,
        android_id=report.android_id,
        receipt=report.receipt,
    )


def has_valid_session(report: ClientReport, now: int | None = None) -> bool:
    current_time = int(time.time()) if now is None else now
    if report.package != PACKAGE_NAME or report.version != 2:
        return False
    if report.expires_at < current_time or report.expires_at > current_time + CHALLENGE_TTL_SECONDS:
        return False
    expected = session_signature(report.challenge, report.expires_at)
    return hmac.compare_digest(report.session, expected)


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/api/config")
def api_config():
    challenge = secrets.token_urlsafe(18)
    expires_at = int(time.time()) + CHALLENGE_TTL_SECONDS
    return {
        "challenge": challenge,
        "expires_at": expires_at,
        "session": session_signature(challenge, expires_at),
        "scheme": "parcel-v2",
    }


@app.post("/api/parcel")
def api_parcel(report: ClientReport):
    if not has_valid_session(report):
        return client_error("bad_session")
    if report.rooted is not False:
        return client_error("rooted_environment")
    return {
        "parcel": sealed_parcel(report.challenge),
        "iv": base64.b64encode(parcel_iv(report.challenge)).decode(),
        "receipt": receipt_for(report),
    }


@app.post("/api/key")
def api_key(request: KeyRequest):
    missing = missing_key_fields(request)
    if missing:
        return {
            "ok": True,
            "message": "key service is alive and waiting for signed route parameters",
            "missing": missing,
        }

    report = key_report(request)
    if not has_valid_session(report):
        return client_error("bad_session")
    if report.rooted is not False:
        return client_error("rooted_environment")
    if not report.receipt or not hmac.compare_digest(report.receipt, receipt_for(report)):
        return client_error("bad_receipt")
    return {
        "key": base64.b64encode(parcel_key(report.challenge)).decode(),
        "algorithm": "parcel-v2",
    }
