"""BYOK connector key encryption (AGENTS section 12).

AES-256-GCM with the CONNECTOR_MASTER_KEY from the environment:

- 32-byte master key, base64-encoded in the env var;
- random 96-bit nonce per encryption, stored alongside the ciphertext;
- AAD binds the ciphertext to workspace + provider so a row copied across
  tenants cannot decrypt;
- key version recorded per row to allow master-key rotation (re-encrypt on
  read during a rotation window);
- the mask (last 4 chars) is computed BEFORE encryption and is the only
  plaintext残留 ever shown anywhere.

No homemade reversible encoding; `cryptography.hazmat` AESGCM only.
"""

from __future__ import annotations

import base64
import os
import secrets
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MASTER_KEY_ENV = "CONNECTOR_MASTER_KEY"
CURRENT_KEY_VERSION = 1
_NONCE_BYTES = 12  # 96-bit, per NIST SP 800-38D


class ConnectorCryptoError(RuntimeError):
    """Configuration or integrity failure in the connector key crypto."""


def _master_key() -> bytes:
    raw = os.getenv(MASTER_KEY_ENV, "").strip()
    if not raw:
        raise ConnectorCryptoError(
            "CONNECTOR_MASTER_KEY is not configured; BYOK connectors are unavailable"
        )
    try:
        key = base64.b64decode(raw, validate=True)
    except Exception as exc:
        raise ConnectorCryptoError("CONNECTOR_MASTER_KEY is not valid base64") from exc
    if len(key) != 32:
        raise ConnectorCryptoError("CONNECTOR_MASTER_KEY must decode to exactly 32 bytes")
    return key


def crypto_available() -> bool:
    """True when a valid master key is configured (route-level gate)."""

    try:
        _master_key()
        return True
    except ConnectorCryptoError:
        return False


def mask_secret(secret: str) -> str:
    """Display mask: never more than the last 4 characters survive."""

    tail = secret[-4:] if len(secret) >= 4 else secret
    return f"\u2022\u2022\u2022\u2022{tail}"


@dataclass(frozen=True, slots=True)
class EncryptedSecret:
    ciphertext: bytes
    nonce: bytes
    key_version: int
    mask: str


def encrypt_secret(secret: str, *, workspace_id: str, provider: str) -> EncryptedSecret:
    """Encrypt one connector API key, AAD-bound to its workspace + provider."""

    if not secret.strip():
        raise ConnectorCryptoError("empty connector secret")
    key = _master_key()
    nonce = secrets.token_bytes(_NONCE_BYTES)
    aad = f"{workspace_id}:{provider}:v{CURRENT_KEY_VERSION}".encode("utf-8")
    ciphertext = AESGCM(key).encrypt(nonce, secret.encode("utf-8"), aad)
    return EncryptedSecret(
        ciphertext=ciphertext,
        nonce=nonce,
        key_version=CURRENT_KEY_VERSION,
        mask=mask_secret(secret),
    )


def decrypt_secret(
    ciphertext: bytes,
    nonce: bytes,
    key_version: int,
    *,
    workspace_id: str,
    provider: str,
) -> str:
    """Decrypt for server-side use only; the plaintext must never be persisted,
    logged, or returned in any response."""

    if key_version != CURRENT_KEY_VERSION:
        raise ConnectorCryptoError(f"unsupported connector key version {key_version}")
    key = _master_key()
    aad = f"{workspace_id}:{provider}:v{key_version}".encode("utf-8")
    try:
        plaintext = AESGCM(key).decrypt(nonce, ciphertext, aad)
    except Exception as exc:
        raise ConnectorCryptoError("connector secret failed integrity check") from exc
    return plaintext.decode("utf-8")
