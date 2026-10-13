"""Cryptographic utilities for token encryption at rest and OAuth state signing."""

import base64
import binascii
import hashlib
import hmac
import json
import time
import uuid
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings
from app.core.errors import AppException
from app.core.logging import get_logger

logger = get_logger("mentor_ai.crypto")


class CryptoException(AppException):
    """Cryptographic operation failure."""

    def __init__(self, detail: str = "Cryptographic operation failed"):
        super().__init__(detail=detail, status_code=500, error_code="CRYPTO_ERROR")


class StateValidationException(AppException):
    """OAuth CSRF state validation failure."""

    def __init__(self, detail: str = "Invalid, expired, or forged OAuth state token"):
        super().__init__(detail=detail, status_code=400, error_code="INVALID_OAUTH_STATE")


def _get_encryption_key() -> bytes:
    """Derive a URL-safe 32-byte Fernet key from configured secret."""
    if settings.CALENDAR_ENCRYPTION_KEY:
        key = settings.CALENDAR_ENCRYPTION_KEY.strip()
        try:
            # Validate if it's already a valid Fernet key
            decoded = base64.urlsafe_b64decode(key)
            if len(decoded) == 32:
                return key.encode("utf-8")
        except (ValueError, binascii.Error) as exc:
            logger.debug(
                "CALENDAR_ENCRYPTION_KEY is not valid 32-byte Fernet key, falling back to derivation",
                error=str(exc),
            )
    # Deterministically derive 32-byte key using SHA-256 on SECRET_KEY
    digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def get_fernet() -> Fernet:
    """Return configured Fernet instance."""
    return Fernet(_get_encryption_key())


def encrypt_token(plain_token: str) -> str:
    """Encrypt a plaintext token (access or refresh token) for secure database storage.

    Args:
        plain_token: Sensitive OAuth token string.

    Returns:
        URL-safe base64-encoded encrypted token string.
    """
    if not plain_token:
        return ""
    try:
        fernet = get_fernet()
        encrypted_bytes = fernet.encrypt(plain_token.encode("utf-8"))
        return encrypted_bytes.decode("utf-8")
    except Exception as exc:
        raise CryptoException(f"Failed to encrypt token: {exc}") from exc


def decrypt_token(encrypted_token: str) -> str:
    """Decrypt an encrypted token retrieved from the database.

    Args:
        encrypted_token: Ciphertext string previously produced by encrypt_token.

    Returns:
        Original plaintext token.
    """
    if not encrypted_token:
        return ""
    try:
        fernet = get_fernet()
        decrypted_bytes = fernet.decrypt(encrypted_token.encode("utf-8"))
        return decrypted_bytes.decode("utf-8")
    except InvalidToken as exc:
        raise CryptoException(
            "Token decryption failed: ciphertext is invalid or tampered."
        ) from exc
    except Exception as exc:
        raise CryptoException(f"Token decryption failed: {exc}") from exc


# -----------------------------------------------------------------------------
# HMAC Signed OAuth State (CSRF Protection)
# -----------------------------------------------------------------------------
def generate_oauth_state(
    user_id: uuid.UUID,
    provider: str = "google_calendar",
    expires_in_seconds: int = 600,
) -> str:
    """Generate a tamper-proof, timestamped, HMAC-signed OAuth state parameter.

    Args:
        user_id: UUID of the user initiating the OAuth flow.
        provider: Target provider name ('google_calendar').
        expires_in_seconds: Time-to-live for state token (default 10 minutes).

    Returns:
        Base64-encoded state parameter with signature.
    """
    payload: dict[str, Any] = {
        "uid": str(user_id),
        "prv": provider,
        "exp": int(time.time()) + expires_in_seconds,
        "nonce": uuid.uuid4().hex,
    }
    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode("utf-8")).decode("utf-8").rstrip("=")

    signature = hmac.new(
        key=settings.SECRET_KEY.encode("utf-8"),
        msg=payload_b64.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()

    return f"{payload_b64}.{signature}"


def verify_oauth_state(state: str, expected_provider: str = "google_calendar") -> uuid.UUID:
    """Verify an OAuth state parameter and return the initiating user's UUID.

    Args:
        state: State string returned by OAuth callback.
        expected_provider: Expected provider matching state payload.

    Returns:
        UUID of the user who initiated the flow.

    Raises:
        StateValidationException: If token is malformed, forged, or expired.
    """
    if not state or "." not in state:
        raise StateValidationException("Malformed state parameter: missing delimiter.")

    parts = state.split(".", 1)
    payload_b64, signature = parts[0], parts[1]

    # Verify HMAC signature
    expected_sig = hmac.new(
        key=settings.SECRET_KEY.encode("utf-8"),
        msg=payload_b64.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(signature, expected_sig):
        raise StateValidationException(
            "OAuth state signature verification failed (tampered token)."
        )

    # Decode JSON payload
    try:
        padded_b64 = payload_b64 + "=" * (-len(payload_b64) % 4)
        payload_bytes = base64.urlsafe_b64decode(padded_b64)
        payload = json.loads(payload_bytes.decode("utf-8"))
    except Exception as exc:
        raise StateValidationException("Failed to decode state payload.") from exc

    # Check expiration
    exp = payload.get("exp", 0)
    if time.time() > exp:
        raise StateValidationException("OAuth state has expired. Please initiate connection again.")

    # Check provider
    if payload.get("prv") != expected_provider:
        raise StateValidationException(
            f"State provider mismatch: expected {expected_provider}, got {payload.get('prv')}."
        )

    # Check user UUID
    uid_str = payload.get("uid")
    if not uid_str:
        raise StateValidationException("State payload missing user ID.")

    try:
        return uuid.UUID(uid_str)
    except ValueError:
        raise StateValidationException("Invalid user UUID in state token.") from None
