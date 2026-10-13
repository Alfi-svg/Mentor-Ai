"""Integration tests for two-phase action approvals, idempotency, and post-condition verification."""

from datetime import UTC, datetime, timedelta
import uuid

from fastapi.testclient import TestClient
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.action_service import ActionService
from tests.backend.conftest import USER_A_ID


def test_list_pending_actions(
    client: TestClient, user_a_headers: dict[str, str], db_session: AsyncSession
) -> None:
    res = client.get("/api/v1/actions/pending", headers=user_a_headers)
    assert res.status_code == 200
    assert isinstance(res.json(), list)


@pytest.mark.asyncio
async def test_stage_action_and_idempotency_protection(
    db_session: AsyncSession,
) -> None:
    key = str(uuid.uuid4())
    payload = {
        "title": "Advising Appointment",
        "start_time": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        "end_time": (datetime.now(UTC) + timedelta(days=1, hours=1)).isoformat(),
    }

    # First staging
    action1 = await ActionService.stage_action(
        db=db_session,
        user_id=USER_A_ID,
        action_type="create_calendar_event",
        payload=payload,
        idempotency_key=key,
    )
    assert action1.status == "pending_approval"

    # Second staging with same idempotency key must return exact same action (duplicate protection)
    action2 = await ActionService.stage_action(
        db=db_session,
        user_id=USER_A_ID,
        action_type="create_calendar_event",
        payload=payload,
        idempotency_key=key,
    )
    assert action1.id == action2.id


def test_confirm_action_approved_and_verified(
    client: TestClient, user_a_headers: dict[str, str]
) -> None:
    # 1. Stage an action via MCP or direct API
    start_dt = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    end_dt = (datetime.now(UTC) + timedelta(days=2, hours=1)).isoformat()

    # Stage using MCP endpoint or direct service
    stage_payload = {
        "user_id": str(USER_A_ID),
        "title": "Machine Learning Lab Presentation",
        "start_time": start_dt,
        "end_time": end_dt,
        "location": "Room 402",
        "idempotency_key": str(uuid.uuid4()),
    }

    import asyncio
    from app.services.mcp.server import mcp_server

    mcp_res = asyncio.run(mcp_server.call_tool("create_calendar_event", stage_payload))
    staged_data = mcp_res.structured_content
    action_id = staged_data["action_id"]

    # Verify action appears in pending actions list
    pending_res = client.get("/api/v1/actions/pending", headers=user_a_headers)
    assert pending_res.status_code == 200
    pending_ids = [a["id"] for a in pending_res.json()]
    assert action_id in pending_ids

    # 2. Confirm the action
    confirm_res = client.post(
        f"/api/v1/actions/{action_id}/confirm",
        json={"confirmed": True},
        headers=user_a_headers,
    )
    assert confirm_res.status_code == 200
    confirm_data = confirm_res.json()
    assert confirm_data["status"] == "completed"
    assert confirm_data["verified"] is True
    assert confirm_data["verification_details"] is not None
    assert "event_id" in confirm_data["verification_details"]

    # 3. Independent post-condition verification
    verify_res = client.get(
        f"/api/v1/actions/{action_id}/verify", headers=user_a_headers
    )
    assert verify_res.status_code == 200
    verify_data = verify_res.json()
    assert verify_data["status"] == "completed"
    assert verify_data["verified"] is True


def test_confirm_action_rejected(
    client: TestClient, user_a_headers: dict[str, str]
) -> None:
    start_dt = (datetime.now(UTC) + timedelta(days=3)).isoformat()
    end_dt = (datetime.now(UTC) + timedelta(days=3, hours=1)).isoformat()

    import asyncio
    from app.services.mcp.server import mcp_server

    mcp_res = asyncio.run(
        mcp_server.call_tool(
            "create_calendar_event",
            {
                "user_id": str(USER_A_ID),
                "title": "Cancelled Study Group",
                "start_time": start_dt,
                "end_time": end_dt,
            },
        )
    )
    action_id = mcp_res.structured_content["action_id"]

    # User explicitly rejects the staged action
    reject_res = client.post(
        f"/api/v1/actions/{action_id}/confirm",
        json={"confirmed": False, "rejection_reason": "No longer needed"},
        headers=user_a_headers,
    )
    assert reject_res.status_code == 200
    data = reject_res.json()
    assert data["status"] == "rejected"
    assert data["verified"] is False
    assert "No longer needed" in data["error_message"]

    # Verification report confirms rejected status
    verify_res = client.get(
        f"/api/v1/actions/{action_id}/verify", headers=user_a_headers
    )
    assert verify_res.status_code == 200
    assert verify_res.json()["verified"] is False


def test_cannot_reprocess_completed_or_rejected_action(
    client: TestClient, user_a_headers: dict[str, str]
) -> None:
    start_dt = (datetime.now(UTC) + timedelta(days=4)).isoformat()
    end_dt = (datetime.now(UTC) + timedelta(days=4, hours=1)).isoformat()

    import asyncio
    from app.services.mcp.server import mcp_server

    mcp_res = asyncio.run(
        mcp_server.call_tool(
            "create_calendar_event",
            {
                "user_id": str(USER_A_ID),
                "title": "Double Action Test",
                "start_time": start_dt,
                "end_time": end_dt,
            },
        )
    )
    action_id = mcp_res.structured_content["action_id"]

    # Confirm once
    res1 = client.post(
        f"/api/v1/actions/{action_id}/confirm",
        json={"confirmed": True},
        headers=user_a_headers,
    )
    assert res1.status_code == 200

    # Attempt to confirm second time -> 400 Bad Request
    res2 = client.post(
        f"/api/v1/actions/{action_id}/confirm",
        json={"confirmed": True},
        headers=user_a_headers,
    )
    assert res2.status_code == 400
    assert res2.json()["error_code"] == "ACTION_ALREADY_PROCESSED"


def test_cross_user_action_isolation(
    client: TestClient,
    user_a_headers: dict[str, str],
    user_b_headers: dict[str, str],
) -> None:
    start_dt = (datetime.now(UTC) + timedelta(days=5)).isoformat()
    end_dt = (datetime.now(UTC) + timedelta(days=5, hours=1)).isoformat()

    import asyncio
    from app.services.mcp.server import mcp_server

    mcp_res = asyncio.run(
        mcp_server.call_tool(
            "create_calendar_event",
            {
                "user_id": str(USER_A_ID),
                "title": "User A Private Event",
                "start_time": start_dt,
                "end_time": end_dt,
            },
        )
    )
    action_id = mcp_res.structured_content["action_id"]

    # User B attempts to confirm User A's action -> 404 Not Found
    res = client.post(
        f"/api/v1/actions/{action_id}/confirm",
        json={"confirmed": True},
        headers=user_b_headers,
    )
    assert res.status_code == 404
