"""Short-lived, server-validated, tamper-evident action approval token engine."""

import base64
import hashlib
import hmac
import json
import time
import uuid
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("mentor_ai.copilot.approval")


def _canonicalize_payload(payload: dict[str, Any]) -> str:
    """Normalize payload fields into a deterministic JSON string for hashing."""
    normalized: dict[str, Any] = {
        "recipient_email": str(payload.get("recipient_email") or payload.get("to") or "").strip().lower(),
        "subject": str(payload.get("subject") or "").strip(),
        "body": str(payload.get("body") or "").strip(),
        "thread_id": str(payload.get("thread_id") or "").strip() or None,
    }
    return json.dumps(normalized, sort_keys=True)


def generate_action_approval(
    user_id: uuid.UUID,
    action_type: str,
    payload: dict[str, Any],
    expires_in_seconds: int = 900,
) -> str:
    """Generate a tamper-evident, short-lived approval token bound to user, action, and exact payload."""
    now_ts = int(time.time())
    exp_ts = now_ts + expires_in_seconds
    canon = _canonicalize_payload(payload)
    payload_hash = hashlib.sha256(canon.encode("utf-8")).hexdigest()

    data = f"{user_id}:{action_type}:{payload_hash}:{exp_ts}"
    key = settings.SECRET_KEY.encode("utf-8")
    sig = hmac.new(key, data.encode("utf-8"), hashlib.sha256).hexdigest()

    combined = f"{data}:{sig}"
    return base64.urlsafe_b64encode(combined.encode("utf-8")).decode("utf-8")


def verify_action_approval(
    approval_id: str,
    user_id: uuid.UUID,
    expected_action_type: str,
    current_payload: dict[str, Any],
) -> tuple[bool, str]:
    """Verify approval token validity, expiration, user boundary, and payload integrity."""
    if not approval_id:
        return False, "Missing approval ID. Action requires explicit approval."

    try:
        decoded = base64.urlsafe_b64decode(approval_id.encode("utf-8")).decode("utf-8")
        parts = decoded.split(":")
        if len(parts) != 5:
            return False, "Malformed approval token."

        token_user_id, token_action, token_hash, exp_ts_str, token_sig = parts
        exp_ts = int(exp_ts_str)

        # 1. Verify HMAC signature
        data = f"{token_user_id}:{token_action}:{token_hash}:{exp_ts_str}"
        key = settings.SECRET_KEY.encode("utf-8")
        expected_sig = hmac.new(key, data.encode("utf-8"), hashlib.sha256).hexdigest()

        if not hmac.compare_digest(token_sig, expected_sig):
            logger.warning("Approval token signature mismatch", user_id=str(user_id))
            return False, "Invalid approval token signature."

        # 2. Check expiration
        now_ts = int(time.time())
        if now_ts > exp_ts:
            return False, "Approval token has expired. Please review and confirm the action again."

        # 3. Check user boundary
        if token_user_id != str(user_id):
            logger.warning("Approval token user mismatch", expected=str(user_id), actual=token_user_id)
            return False, "Approval token belongs to a different user session."

        # 4. Check action type
        if token_action != expected_action_type:
            return False, f"Approval token is for action '{token_action}', expected '{expected_action_type}'."

        # 5. Check exact payload integrity (draft changed detection)
        current_canon = _canonicalize_payload(current_payload)
        current_hash = hashlib.sha256(current_canon.encode("utf-8")).hexdigest()

        if not hmac.compare_digest(token_hash, current_hash):
            return False, "Draft content or recipient was modified after approval was generated. Please confirm the updated draft."

        return True, "Approval verified."

    except Exception as exc:
        logger.error("Error verifying approval token", error=str(exc))
        return False, f"Failed to verify approval token: {exc}"
