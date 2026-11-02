#!/usr/bin/env python3
import base64
import json
import time
import unittest

import server


def error_body(response):
    return json.loads(response.body.decode())


def decrypt_parcel(ciphertext, key, iv):
    plaintext = bytearray()
    previous = iv
    for offset in range(0, len(ciphertext), 16):
        block = ciphertext[offset : offset + 16]
        plaintext.extend(server.xor_block(server.xor_block(block, key), previous))
        previous = block
    pad_len = plaintext[-1]
    return bytes(plaintext[:-pad_len])


class ProtocolTest(unittest.TestCase):
    def report(self, rooted=False):
        config = server.api_config()
        return server.ClientReport(
            package=server.PACKAGE_NAME,
            version=2,
            challenge=config["challenge"],
            expires_at=config["expires_at"],
            session=config["session"],
            rooted=rooted,
            fingerprint="test-fingerprint",
            model="test-model",
            android_id="test-device",
        )

    def test_happy_path_decrypts_flag(self):
        report = self.report()
        parcel = server.api_parcel(report)
        report.receipt = parcel["receipt"]
        key_response = server.api_key(report)
        plaintext = decrypt_parcel(
            base64.b64decode(parcel["parcel"]),
            base64.b64decode(key_response["key"]),
            base64.b64decode(parcel["iv"]),
        )
        self.assertEqual(plaintext.decode(), server.FLAG)

    def test_rooted_client_is_rejected_before_parcel(self):
        response = server.api_parcel(self.report(rooted=True))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(error_body(response), {"error": "rooted_environment"})

    def test_key_requires_matching_receipt(self):
        report = self.report()
        server.api_parcel(report)
        report.receipt = "tampered"
        response = server.api_key(report)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(error_body(response), {"error": "bad_receipt"})

    def test_empty_key_probe_does_not_return_key(self):
        response = server.api_key(server.KeyRequest(
            package=server.PACKAGE_NAME,
            version=2,
            rooted=False,
        ))
        self.assertEqual(response["ok"], True)
        self.assertEqual(
            response["message"],
            "key service is alive and waiting for signed route parameters",
        )
        self.assertEqual(response["missing"], [
            "challenge",
            "expires_at",
            "session",
            "receipt",
        ])
        self.assertNotIn("key", response)

    def test_expired_session_is_rejected(self):
        report = self.report()
        report.expires_at = int(time.time()) - 1
        report.session = server.session_signature(report.challenge, report.expires_at)
        response = server.api_parcel(report)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(error_body(response), {"error": "bad_session"})

    def test_receipt_is_bound_to_device_report(self):
        report = self.report()
        parcel = server.api_parcel(report)
        report.receipt = parcel["receipt"]
        report.android_id = "another-device"
        response = server.api_key(report)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(error_body(response), {"error": "bad_receipt"})


if __name__ == "__main__":
    unittest.main()
