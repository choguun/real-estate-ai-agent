"""T-801 — TOTP secret storage (cycle 8 AC-MFA-01..04, helper tests).

4 helper tests covering:

- TOTP secret generation shape (160 bits, base32)
- Fernet encrypt → decrypt round-trip returns the original
- Decrypt with a wrong Fernet key raises InvalidToken
- TOTP verify with current code: pass

The endpoint tests (enroll, verify, recovery, login integration)
are added in T-802 / T-803. This file is extended as cycle 8
progresses.
"""

from __future__ import annotations

import time

import pyotp
import pytest
from cryptography.fernet import Fernet, InvalidToken

from app.mfa import (
    decrypt_secret,
    encrypt_secret,
    generate_totp_secret,
    verify_totp,
)


@pytest.fixture
def fernet() -> Fernet:
    """A fresh Fernet instance per test (deterministic key)."""
    return Fernet(Fernet.generate_key())


# ── Secret generation shape ─────────────────────────────────────────


def test_generate_totp_secret_shape() -> None:
    """A TOTP secret is 160 bits (20 bytes), base32-encoded
    without padding. 20 bytes = 32 base32 chars.
    """
    secret = generate_totp_secret()
    # 20 bytes = ceil(20 * 8 / 5) = 32 base32 chars (no padding)
    assert len(secret) == 32, f"expected 32 chars, got {len(secret)}: {secret!r}"
    # All chars are valid base32 (A-Z, 2-7)
    for c in secret:
        assert c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567", f"invalid base32 char: {c!r}"


def test_generate_totp_secret_is_unique() -> None:
    """Two calls produce different secrets (high entropy)."""
    a = generate_totp_secret()
    b = generate_totp_secret()
    assert a != b


# ── Encrypt + decrypt round-trip ─────────────────────────────────────


def test_encrypt_decrypt_round_trip(fernet: Fernet) -> None:
    """Encrypting a secret and decrypting it returns the original."""
    plain = generate_totp_secret()
    cipher = encrypt_secret(plain, fernet=fernet)
    assert cipher != plain  # ciphertext != plaintext
    assert decrypt_secret(cipher, fernet=fernet) == plain


def test_decrypt_with_wrong_key_raises(fernet: Fernet) -> None:
    """Decrypting with a different Fernet key raises InvalidToken
    (defensive: a leaked DB row can't be decrypted without
    the production key).
    """
    plain = generate_totp_secret()
    cipher = encrypt_secret(plain, fernet=fernet)

    other_fernet = Fernet(Fernet.generate_key())
    with pytest.raises(InvalidToken):
        decrypt_secret(cipher, fernet=other_fernet)


# ── TOTP verify (helper-level) ───────────────────────────────────────


def test_verify_totp_with_current_code_passes(fernet: Fernet) -> None:
    """The verify helper accepts the current TOTP code (the code
    that the authenticator app is showing right now).
    """
    secret = generate_totp_secret()
    encrypted = encrypt_secret(secret, fernet=fernet)
    decrypted = decrypt_secret(encrypted, fernet=fernet)

    # Compute the current TOTP code using the same secret
    totp = pyotp.TOTP(decrypted)
    current_code = totp.now()

    assert verify_totp(decrypted, current_code) is True


def test_verify_totp_with_random_code_fails() -> None:
    """The verify helper rejects a wrong 6-digit code."""
    secret = generate_totp_secret()
    # '000000' is the standard invalid test code (authenticator
    # apps never generate it; verify is expected to fail).
    assert verify_totp(secret, "000000") is False


def test_verify_totp_with_expired_code_fails(fernet: Fernet) -> None:
    """A TOTP code from >90 seconds ago is rejected (±1 step
    window per RFC 6238).
    """
    secret = generate_totp_secret()
    totp = pyotp.TOTP(secret)

    # Compute a code from "now - 5 minutes" by manually stepping
    # the time. pyotp's at(for_time) lets us get a code for any
    # timestamp.
    long_ago = time.time() - 300  # 5 minutes ago
    old_code = totp.at(long_ago)

    # That code's validity window was [-30, +30] sec around
    # long_ago, which is well outside the ±90s window from now.
    assert verify_totp(secret, old_code) is False
