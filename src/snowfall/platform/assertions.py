"""Underworld server-signed, short-lived login assertions (never passwords).

Wire format: base64url(canonical JSON UTF-8) + '.' +
base64url(HMAC-SHA256(secret, ASCII encoded JSON segment)).
The Underworld backend generates the assertion after authenticating the user's
existing account and its one character. The browser must not sign anything.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import json
import re
import time


class AssertionError(ValueError):
    pass


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _decode(segment: str) -> bytes:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", segment):
        raise AssertionError("Invalid assertion encoding")
    return base64.b64decode(segment + "=" * (-len(segment) % 4), altchars=b"-_", validate=True)


@dataclass(frozen=True)
class UnderworldAssertion:
    account_id: str
    character_id: str
    character_name: str
    nonce: str
    expires_at: datetime


def parse_underworld_assertion(token: str, secret: str, *, now: int | None = None
                               ) -> UnderworldAssertion:
    if len(secret.encode("utf-8")) < 32:
        raise AssertionError("Underworld signing secret must be at least 32 bytes")
    if not isinstance(token, str) or len(token) > 4096 or token.count(".") != 1:
        raise AssertionError("Invalid assertion")
    raw, signature = token.split(".")
    expected = hmac.new(secret.encode("utf-8"), raw.encode("ascii"), hashlib.sha256).digest()
    try:
        supplied = _decode(signature)
        payload = json.loads(_decode(raw))
    except (ValueError, UnicodeDecodeError, TypeError, OverflowError) as exc:
        raise AssertionError("Invalid assertion encoding") from exc
    if not hmac.compare_digest(expected, supplied):
        raise AssertionError("Invalid assertion signature")
    if not isinstance(payload, dict) or payload.get("iss") != "underworld" or (
        payload.get("aud") != "operation-snowfall"
    ):
        raise AssertionError("Wrong assertion issuer or audience")
    issued, expiry = payload.get("iat"), payload.get("exp")
    t = int(time.time()) if now is None else now
    if (type(issued) is not int or type(expiry) is not int
            or issued > t + 30 or issued < t - 120
            or expiry <= t or expiry > issued + 120 or expiry <= issued):
        raise AssertionError("Expired or invalid assertion timestamps")
    values = []
    for key, maximum in (("account_id", 128), ("character_id", 128),
                         ("character_name", 120), ("jti", 128)):
        value = payload.get(key)
        if not isinstance(value, str) or not 1 <= len(value.strip()) <= maximum:
            raise AssertionError("Missing or invalid assertion field: " + key)
        if any(ord(ch) < 32 for ch in value):
            raise AssertionError("Invalid assertion field: " + key)
        values.append(value)
    return UnderworldAssertion(values[0], values[1], values[2], values[3],
                               datetime.fromtimestamp(expiry, tz=timezone.utc))


def sign_underworld_assertion(payload: dict, secret: str) -> str:
    """Helper for the trusted Underworld backend and integration tests only."""
    if len(secret.encode("utf-8")) < 32:
        raise AssertionError("Signing secret must be at least 32 bytes")
    raw = _b64(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
    return raw + "." + _b64(hmac.new(secret.encode(), raw.encode("ascii"),
                                    hashlib.sha256).digest())
