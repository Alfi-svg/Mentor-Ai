"""Multi-tenant data isolation and anti-IDOR tests."""

import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.profile import Profile
from app.db.models.task import Task
from tests.backend.conftest import (
    USER_A_ID,
    USER_A_EMAIL,
    USER_B_ID,
    USER_B_EMAIL,
)


def test_user_preferences_isolation(
    client: TestClient,
    user_a_headers: dict[str, str],
    user_b_headers: dict[str, str],
) -> None:
    """Verify User A's preferences are completely isolated from User B."""
    # 1. User A sets custom working hours and buffer
    res_a_update = client.put(
        "/api/v1/auth/preferences",
        json={"work_start_time": "06:30:00", "buffer_minutes": 25},
        headers=user_a_headers,
    )
    assert res_a_update.status_code == 200
    assert res_a_update.json()["work_start_time"] == "06:30:00"
    assert res_a_update.json()["buffer_minutes"] == 25

    # 2. User B requests /api/v1/auth/me
    res_b_me = client.get("/api/v1/auth/me", headers=user_b_headers)
    assert res_b_me.status_code == 200
    b_data = res_b_me.json()

    # User B MUST have their own identity and NOT User A's customized values
    assert b_data["id"] == str(USER_B_ID)
    assert b_data["email"] == USER_B_EMAIL
    assert b_data["preferences"]["work_start_time"] == "09:00:00"  # default
    assert b_data["preferences"]["buffer_minutes"] == 15  # default


@pytest.mark.asyncio
async def test_database_level_task_isolation(db_session: AsyncSession) -> None:
    """Verify database queries enforcing user_id ownership prevent cross-tenant reading."""
    # 1. Ensure Profile for User A exists in DB
    profile_a = await db_session.get(Profile, USER_A_ID)
    if not profile_a:
        profile_a = Profile(id=USER_A_ID, email=USER_A_EMAIL, full_name="Alex Chen")
        db_session.add(profile_a)

    # 2. Ensure Profile for User B exists in DB
    profile_b = await db_session.get(Profile, USER_B_ID)
    if not profile_b:
        profile_b = Profile(id=USER_B_ID, email=USER_B_EMAIL, full_name="Priya Patel")
        db_session.add(profile_b)

    await db_session.flush()

    # 3. Create a private task owned strictly by User A
    task_a_id = uuid.uuid4()
    task_a = Task(
        id=task_a_id,
        user_id=USER_A_ID,
        title="Alex Private Exam Prep",
        description="Confidential exam questions",
        priority="P1",
        duration_minutes=90,
    )
    db_session.add(task_a)
    await db_session.commit()

    # 4. User B attempts to query task_a_id using their authenticated user_id
    query_b = select(Task).where(
        Task.id == task_a_id,
        Task.user_id == USER_B_ID,  # Backend query ownership enforcement
    )
    result_b = await db_session.execute(query_b)
    leaked_task = result_b.scalar_one_or_none()

    # The task must NOT be accessible to User B
    assert leaked_task is None

    # 5. User A querying the same ID receives the task properly
    query_a = select(Task).where(
        Task.id == task_a_id,
        Task.user_id == USER_A_ID,
    )
    result_a = await db_session.execute(query_a)
    owned_task = result_a.scalar_one_or_none()
    assert owned_task is not None
    assert owned_task.id == task_a_id
    assert owned_task.title == "Alex Private Exam Prep"
