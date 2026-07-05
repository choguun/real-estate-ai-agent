"""TOTP MFA helpers — cycle 8 T-801.

The MFA foundation: TOTP secret generation, Fernet encryption
for at-rest storage, and TOTP verification.

## Why TOTP

TOTP (RFC 6238) is the universal second factor. Every
authenticator app (Google Authenticator, Authy, 1Password,
Bitwarden, ...) speaks the same protocol: a 6-digit code that
rotates every 30 seconds, derived from a shared secret + the
current time. The secret is provisioned once via a QR code
(the `otpauth://` URI); thereafter the user just reads the
current code from their phone.

## Why Fernet

The TOTP secret is what an attacker needs to generate valid
codes. Storing it in plaintext in the DB is unacceptable.
Fernet (cryptography.io's symmetric encryption) gives us:

- AES-128-CBC + HMAC-SHA256 in a single primitive
- Aversion to nonce reuse via the format's version byte
- 32-byte key that we can derive from a single env var

## Why pyotp

pyotp is the standard Python TOTP library. It implements RFC
6238 verbatim, including the ±1 step window (90 seconds
total validity) and the HMAC-SHA1 default. We don't roll our
own crypto.
"""

from __future__ import annotations

import base64
import os
from typing import Final

import pyotp
from cryptography.fernet import Fernet

# RFC 6238 §5.1: "The HOTP/TOTP secret is typically 160 bits."
# 20 bytes = 160 bits.
_TOTP_SECRET_BYTES: Final[int] = 20

# RFC 6238 §5.2 default valid_time_window = 1 (i.e., ±1 step
# = 90 seconds total). pyotp accepts this directly.
_TOTP_VALID_WINDOW: Final[int] = 1


def generate_totp_secret() -> str:
    """Generate a 160-bit TOTP secret, base32-encoded.

    Returns:
        A 32-character base32 string (no padding). Compatible
        with every standard authenticator app via the
        `otpauth://totp/...?secret={...}` URI format.
    """
    raw = os.urandom(_TOTP_SECRET_BYTES)
    return base64.b32encode(raw).decode("ascii").rstrip("=")


def encrypt_secret(plaintext: str, *, fernet: Fernet) -> str:
    """Encrypt a TOTP secret for at-rest storage.

    Args:
        plaintext: The 32-character base32 TOTP secret.
        fernet: A configured Fernet instance (typically
            constructed from `Settings.mfa_encryption_key`).

    Returns:
        A URL-safe base64-encoded ciphertext suitable for
        storing in a TEXT column. Decryptable only with the
        same Fernet key.
    """
    return fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_secret(ciphertext: str, *, fernet: Fernet) -> str:
    """Decrypt a TOTP secret from at-rest storage.

    Args:
        ciphertext: The Fernet-encrypted ciphertext from the DB.
        fernet: The same Fernet instance (or one with the same
            underlying key) used to encrypt.

    Returns:
        The plaintext TOTP secret.

    Raises:
        cryptography.fernet.InvalidToken: If the ciphertext
            was tampered with or encrypted with a different key.
    """
    return fernet.decrypt(ciphertext.encode("utf-8")).decode("ascii")


def verify_totp(secret: str, code: str) -> bool:
    """Verify a 6-digit TOTP code against a secret.

    Uses pyotp's TOTP.verify() with the RFC 6238 default
    ±1 step window (90 seconds total validity). Codes are
    case-insensitive + whitespace-stripped (pyotp handles
    both).

    Args:
        secret: The plaintext TOTP secret.
        code: The 6-digit code from the user's authenticator app.

    Returns:
        True if the code is valid (within the validity window),
        False otherwise. A wrong code, an expired code, and
        a replayed code all return False.
    """
    if not code or not secret:
        return False
    try:
        totp = pyotp.TOTP(secret)
        return totp.verify(code, valid_window=_TOTP_VALID_WINDOW)
    except Exception:  # noqa: BLE001 — pyotp raises on garbage input
        return False


def build_fernet_from_key(mfa_encryption_key: str) -> Fernet:
    """Build a Fernet instance from the Settings.mfa_encryption_key.

    The key must be a 32-byte URL-safe base64-encoded string
    (44 chars including padding). The cycle-5 validator
    (`validate_mfa_encryption_key`) enforces this shape in
    non-dev environments.
    """
    return Fernet(mfa_encryption_key.encode("utf-8"))


def current_totp_code(secret: str) -> str:
    """Compute the current 6-digit TOTP code for a secret.

    Exposed for the test suite (so tests don't have to import
    pyotp directly) and for the future WebAuthn cycle that
    might want to issue a TOTP fallback.

    Args:
        secret: The plaintext TOTP secret.

    Returns:
        The 6-digit code currently valid for this secret.
    """
    return pyotp.TOTP(secret).now()
