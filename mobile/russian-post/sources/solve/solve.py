#!/usr/bin/env python3
import argparse
import base64
import json
import ssl
import urllib.request
import xml.etree.ElementTree as ET


def post_json(url, body, context=None):
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5, context=context) as response:
        return json.loads(response.read().decode())


def load_preferences(path):
    values = {}
    for item in ET.parse(path).getroot():
        name = item.attrib["name"]
        if item.tag == "string":
            values[name] = item.text or ""
        elif item.tag in ("int", "long"):
            values[name] = int(item.attrib["value"])
        elif item.tag == "boolean":
            values[name] = item.attrib["value"].lower() == "true"
    return values


def require(preferences, name):
    if name not in preferences:
        raise KeyError(f"missing preference: {name}")
    return preferences[name]


def xor_block(left, right):
    return bytes(a ^ b for a, b in zip(left, right))


def decrypt_parcel(ciphertext, key, iv):
    if not ciphertext or len(ciphertext) % 16 != 0:
        raise ValueError("invalid ciphertext length")
    out = bytearray()
    previous = iv
    for offset in range(0, len(ciphertext), 16):
        block = ciphertext[offset : offset + 16]
        out.extend(xor_block(xor_block(block, key), previous))
        previous = block
    pad_len = out[-1]
    if pad_len < 1 or pad_len > 16 or out[-pad_len:] != bytes([pad_len]) * pad_len:
        raise ValueError("invalid padding")
    return bytes(out[:-pad_len])


def build_report(preferences):
    return {
        "package": require(preferences, "package"),
        "version": require(preferences, "version"),
        "challenge": require(preferences, "challenge"),
        "expires_at": require(preferences, "expires_at"),
        "session": require(preferences, "session"),
        "rooted": False,
        "fingerprint": require(preferences, "fingerprint"),
        "model": require(preferences, "model"),
        "android_id": require(preferences, "android_id"),
        "receipt": require(preferences, "receipt"),
    }


def solve_preferences(preferences, base_url, context=None):
    key_response = post_json(
        base_url.rstrip("/") + "/api/key", build_report(preferences), context=context
    )
    return decrypt_parcel(
        base64.b64decode(require(preferences, "sealed_parcel")),
        base64.b64decode(key_response["key"]),
        base64.b64decode(require(preferences, "iv")),
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prefs", required=True, help="parcel.xml extracted as root")
    parser.add_argument("--base-url", required=True, help="backend base URL")
    parser.add_argument("--ca-cert", help="CA/server certificate for self-signed HTTPS")
    args = parser.parse_args()

    preferences = load_preferences(args.prefs)
    context = ssl.create_default_context(cafile=args.ca_cert) if args.ca_cert else None
    plaintext = solve_preferences(preferences, args.base_url, context=context)
    print(plaintext.decode())


if __name__ == "__main__":
    main()
