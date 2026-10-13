from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient
import pytest

from app.core.config import settings
from app.services.mcp.server import mcp_server
from tests.backend.conftest import USER_A_ID


@pytest.mark.asyncio
async def test_mcp_catalog_exposes_exactly_8_tools() -> None:
    tools = await mcp_server.list_tools()
    tool_names = sorted([t.name for t in tools])
    expected = sorted(
        [
            "get_user_context",
            "list_tasks",
            "create_task",
            "update_task",
            "get_calendar_events",
            "create_calendar_event",
            "generate_schedule",
            "verify_action",
        ]
    )
    assert tool_names == expected
    assert len(tools) == 8


@pytest.mark.asyncio
async def test_mcp_get_user_context() -> None:
    res = await mcp_server.call_tool("get_user_context", {"user_id": str(USER_A_ID)})
    assert res.is_error is False
    data = res.structured_content

    assert data["user_id"] == str(USER_A_ID)
    assert data["timezone"] == "America/New_York"
    assert isinstance(data["work_start_time"], str) and ":" in data["work_start_time"]
    assert isinstance(data["work_end_time"], str) and ":" in data["work_end_time"]
    assert isinstance(data["buffer_minutes"], int) and data["buffer_minutes"] > 0
    assert "pending_tasks_count" in data
    assert isinstance(data["pending_tasks_count"], int)


@pytest.mark.asyncio
async def test_mcp_create_task_and_list_tasks() -> None:
    # 1. Create task via MCP
    create_res = await mcp_server.call_tool(
        "create_task",
        {
            "user_id": str(USER_A_ID),
            "title": "Study Distributed Systems",
            "duration_minutes": 90,
            "priority": "P1",
            "description": "Raft consensus algorithm",
        },
    )
    assert create_res.is_error is False
    created = create_res.structured_content
    task_id = created["task_id"]
    assert created["title"] == "Study Distributed Systems"
    assert created["duration_minutes"] == 90
    assert created["priority"] == "P1"

    # 2. List tasks via MCP
    list_res = await mcp_server.call_tool(
        "list_tasks",
        {"user_id": str(USER_A_ID), "priority": "P1"},
    )
    assert list_res.is_error is False
    tasks = list_res.structured_content["tasks"]
    assert any(t["id"] == task_id for t in tasks)


@pytest.mark.asyncio
async def test_mcp_update_task() -> None:
    # Create task
    create_res = await mcp_server.call_tool(
        "create_task",
        {
            "user_id": str(USER_A_ID),
            "title": "Draft Presentation",
            "duration_minutes": 45,
            "priority": "P3",
        },
    )
    task_id = create_res.structured_content["task_id"]

    # Update status to in_progress
    update_res = await mcp_server.call_tool(
        "update_task",
        {
            "user_id": str(USER_A_ID),
            "task_id": task_id,
            "status": "in_progress",
            "priority": "P2",
        },
    )
    assert update_res.is_error is False
    updated = update_res.structured_content
    assert updated["status"] == "in_progress"
    assert updated["priority"] == "P2"


@pytest.mark.asyncio
async def test_mcp_calendar_events_and_two_phase_staging() -> None:
    now = datetime.now(UTC)
    start_iso = (now + timedelta(days=1, hours=2)).isoformat()
    end_iso = (now + timedelta(days=1, hours=3)).isoformat()

    # 1. Staging calendar event via MCP
    stage_res = await mcp_server.call_tool(
        "create_calendar_event",
        {
            "user_id": str(USER_A_ID),
            "title": "Advising Session",
            "start_time": start_iso,
            "end_time": end_iso,
            "location": "Zoom",
        },
    )
    assert stage_res.is_error is False
    staged = stage_res.structured_content
    assert staged["status"] == "staged_pending_approval"
    assert staged["requires_human_approval"] is True
    action_id = staged["action_id"]

    # 2. Querying calendar events should NOT return the staged event yet
    get_res = await mcp_server.call_tool(
        "get_calendar_events",
        {
            "user_id": str(USER_A_ID),
            "start_time": (now + timedelta(days=1)).isoformat(),
            "end_time": (now + timedelta(days=2)).isoformat(),
        },
    )
    assert get_res.is_error is False
    events = get_res.structured_content["events"]
    assert not any(e["title"] == "Advising Session" for e in events)

    # 3. Verify action returns verified=False before confirmation
    verify_res = await mcp_server.call_tool(
        "verify_action",
        {"user_id": str(USER_A_ID), "action_id": action_id},
    )
    assert verify_res.structured_content["verified"] is False


@pytest.mark.asyncio
async def test_mcp_generate_schedule() -> None:
    target_date = (datetime.now(UTC).date() + timedelta(days=1)).isoformat()
    res = await mcp_server.call_tool(
        "generate_schedule",
        {
            "user_id": str(USER_A_ID),
            "target_date": target_date,
            "enforce_buffer": True,
        },
    )
    assert res.is_error is False
    proposal = res.structured_content
    assert proposal["target_date"] == target_date
    assert proposal["status"] in ["feasible", "conflict_detected"]
    assert "blocks" in proposal


@pytest.mark.asyncio
async def test_mcp_malformed_arguments_handling() -> None:
    # Invalid UUID format should raise error or return error
    with pytest.raises(Exception):
        await mcp_server.call_tool("get_user_context", {"user_id": "not-a-valid-uuid"})


def test_mcp_remote_auth_middleware(
    client: TestClient, user_a_headers: dict[str, str]
) -> None:
    # Test unauthenticated request to /mcp when ENVIRONMENT is production
    with patch.object(settings, "ENVIRONMENT", "production"):
        # Without token -> 401 Unauthorized
        res_unauth = client.get("/mcp/messages/")
        assert res_unauth.status_code == 401

        # With malformed token -> 401 Unauthorized
        res_bad = client.get(
            "/mcp/messages/",
            headers={"Authorization": "Bearer malformed.jwt.token"},
        )
        assert res_bad.status_code == 401

        # With valid Bearer token -> Passes auth guard (reaches underlying route handler)
        res_auth = client.get("/mcp/messages/", headers=user_a_headers)
        assert res_auth.status_code in [400, 405]
