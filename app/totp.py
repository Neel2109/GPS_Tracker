import base64
import hashlib
import hmac
import re
import secrets
import struct
import time
from urllib.parse import quote

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings

TOTP_PERIOD_SECONDS = 30
TOTP_DIGITS = 6
TOTP_WINDOW_STEPS = 1
ISSUER = "TrackGuard"


def generate_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _secret_bytes(secret: str) -> bytes:
    normalized = secret.strip().replace(" ", "").upper()
    return base64.b32decode(normalized + "=" * (-len(normalized) % 8))


def matching_totp_counter(secret: str, code: str, timestamp: float | None = None) -> int | None:
    if not re.fullmatch(r"[0-9]{6}", code):
        return None

    current_step = int((time.time() if timestamp is None else timestamp) // TOTP_PERIOD_SECONDS)
    secret_bytes = _secret_bytes(secret)
    matched_counter = None
    for offset in range(-TOTP_WINDOW_STEPS, TOTP_WINDOW_STEPS + 1):
        counter = current_step + offset
        if counter < 0:
            continue
        digest = hmac.new(secret_bytes, struct.pack(">Q", counter), hashlib.sha1).digest()
        index = digest[-1] & 0x0F
        value = struct.unpack(">I", digest[index:index + 4])[0] & 0x7FFFFFFF
        expected = f"{value % (10 ** TOTP_DIGITS):0{TOTP_DIGITS}d}"
        if hmac.compare_digest(expected, code):
            matched_counter = counter
    return matched_counter


def verify_totp(secret: str, code: str, timestamp: float | None = None) -> bool:
    return matching_totp_counter(secret, code, timestamp) is not None


def encrypt_totp_secret(secret: str) -> str:
    encryption_secret = settings.totp_encryption_key or settings.jwt_secret
    key_material = hashlib.sha256(
        encryption_secret.encode("utf-8") + b":trackguard-totp-secret"
    ).digest()
    key = base64.urlsafe_b64encode(key_material)
    return Fernet(key).encrypt(secret.encode("ascii")).decode("ascii")


def decrypt_totp_secret(encrypted_secret: str) -> str:
    encryption_secret = settings.totp_encryption_key or settings.jwt_secret
    key_material = hashlib.sha256(
        encryption_secret.encode("utf-8") + b":trackguard-totp-secret"
    ).digest()
    key = base64.urlsafe_b64encode(key_material)
    try:
        return Fernet(key).decrypt(encrypted_secret.encode("ascii")).decode("ascii")
    except InvalidToken as error:
        raise ValueError("Could not decrypt the authenticator secret; check JWT_SECRET.") from error


def provisioning_uri(secret: str, account_name: str) -> str:
    label = quote(f"{ISSUER}:{account_name}", safe="")
    issuer = quote(ISSUER, safe="")
    return (
        f"otpauth://totp/{label}?secret={secret}&issuer={issuer}"
        f"&algorithm=SHA1&digits={TOTP_DIGITS}&period={TOTP_PERIOD_SECONDS}"
    )
