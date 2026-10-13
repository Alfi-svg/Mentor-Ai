"""Integration tests for Planner & Chat API endpoints with Day 5 deterministic scheduler integration."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient


# -----------------------------------------------------------------------------
# 1. Draft Plan Generation & Dry-Run Preview
# -----------------------------------------------------------------------------


def test_generate_draft_plan_success_with_preview(
    client: TestClient, user_a_headers: dict[str, str]
) -> None:
    payload = {
        "message": (
            "Plan my day tomorrow: algorithms class from 10am to 11:30am, "
            "team sync 2pm to 3pm, and 2 hours for compiler assignment."
        ),
        "client_timezone": "America/New_York",
    }
    response = client.post(
        "/api/v1/planner/draft", json=payload, headers=user_a_headers
    )
    assert response.status_code == 200
    data = response.json()

    assert data["intent"] == "plan_day"
    assert data["requires_confirmation"] is True
    assert data["parser_used"] in ["deterministic_offline", "gemini", "groq"]
    assert len(data["fixed_events"]) == 2
    assert len(data["tasks"]) == 1
    assert data["tasks"][0]["duration_minutes"] == 120

    # Ensure Day 5 deterministic preview schedule is populated
    preview = data["preview_schedule"]
    assert preview is not None
    assert preview["status"] in ["feasible", "conflict_detected"]
    assert len(preview["blocks"]) >= 3  # 2 fixed events + buffer + task

    # Verify no tasks were persisted yet (dry-run check)
    tasks_res = client.get("/api/v1/tasks", headers=user_a_headers)
    assert tasks_res.status_code == 200
    # The new compiler assignment should NOT exist in database yet
    existing_titles = [t["title"].lower() for t in tasks_res.json()["items"]]
    assert not any("compiler assignment" in t for t in existing_titles)


def test_generate_draft_plan_missing_duration_requires_clarification(
    client: TestClient, user_a_headers: dict[str, str]
) -> None:
    payload = {
        "message": "I need to complete my database lab and review lecture slides tomorrow.",
        "client_timezone": "America/New_York",
    }
    response = client.post(
        "/api/v1/planner/draft", json=payload, headers=user_a_headers
    )
    assert response.status_code == 200
    data = response.json()

    assert data["requires_confirmation"] is False
    assert len(data["missing_information"]) > 0
    assert data["clarification_question"] is not None
    assert "how much time" in data["clarification_question"].lower()
    # Preview schedule MUST be None when durations are missing
    assert data["preview_schedule"] is None


def test_chat_message_endpoint_alias(
    client: TestClient, user_a_headers: dict[str, str]
) -> None:
    payload = {
        "message": "Plan tomorrow: machine learning class 9am to 10:30am and 90 mins for homework.",
        "client_timezone": "America/New_York",
    }
    response = client.post("/api/v1/chat/message", json=payload, headers=user_a_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "plan_day"
    assert len(data["tasks"]) == 1
    assert data["tasks"][0]["duration_minutes"] == 90


# -----------------------------------------------------------------------------
# 2. Plan Confirmation & Activation Pipeline
# -----------------------------------------------------------------------------


def test_confirm_plan_persists_tasks_and_activates_schedule(
    client: TestClient, user_a_headers: dict[str, str]
) -> None:
    target_date = (datetime.now(UTC).date() + timedelta(days=1)).isoformat()
    now_utc = datetime.now(UTC)

    confirm_payload = {
        "target_date": target_date,
        "tasks": [
            {
                "title": "Study Operating Systems Virtual Memory",
                "duration_minutes": 90,
                "priority": "P1",
                "description": "Paging and translation lookaside buffer",
            },
            {
                "title": "Prepare Presentation Slides",
                "duration_minutes": 60,
                "priority": "P2",
            },
        ],
        "fixed_events": [
            {
                "title": "CS301 Lecture",
                "start_time": (now_utc + timedelta(days=1, hours=2)).isoformat(),
                "end_time": (
                    now_utc + timedelta(days=1, hours=3, minutes=30)
                ).isoformat(),
                "location": "Auditorium A",
            }
        ],
        "persist_tasks": True,
        "generate_schedule": True,
    }

    response = client.post(
        "/api/v1/planner/confirm", json=confirm_payload, headers=user_a_headers
    )
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "confirmed"
    assert len(data["created_tasks"]) == 2
    assert len(data["created_events"]) == 1
    assert data["persisted_schedule_id"] is not None
    assert data["schedule"] is not None

    # Verify tasks are now listed in task management endpoint
    tasks_res = client.get("/api/v1/tasks", headers=user_a_headers)
    assert tasks_res.status_code == 200
    task_titles = [t["title"] for t in tasks_res.json()["items"]]
    assert "Study Operating Systems Virtual Memory" in task_titles
    assert "Prepare Presentation Slides" in task_titles

    # Verify schedule endpoint retrieves the newly activated schedule
    sched_res = client.get(f"/api/v1/schedule/{target_date}", headers=user_a_headers)
    assert sched_res.status_code == 200
    sched_data = sched_res.json()
    assert sched_data["target_date"] == target_date
    assert sched_data["status"] == "accepted"
    assert len(sched_data["blocks"]) > 0


# -----------------------------------------------------------------------------
# 3. Security & Multi-Tenant Isolation
# -----------------------------------------------------------------------------


def test_planner_endpoints_reject_unauthenticated_requests(client: TestClient) -> None:
    # 401 on draft
    res_draft = client.post("/api/v1/planner/draft", json={"message": "Plan my day"})
    assert res_draft.status_code == 401

    # 401 on confirm
    res_confirm = client.post(
        "/api/v1/planner/confirm",
        json={"target_date": "2026-10-15", "tasks": []},
    )
    assert res_confirm.status_code == 401


def test_user_isolation_on_plan_confirmation(
    client: TestClient,
    user_a_headers: dict[str, str],
    user_b_headers: dict[str, str],
) -> None:
    target_date = (datetime.now(UTC).date() + timedelta(days=1)).isoformat()

    # User A confirms a plan
    client.post(
        "/api/v1/planner/confirm",
        json={
            "target_date": target_date,
            "tasks": [
                {
                    "title": "User A Private Study",
                    "duration_minutes": 60,
                    "priority": "P1",
                }
            ],
            "persist_tasks": True,
            "generate_schedule": True,
        },
        headers=user_a_headers,
    )

    # User B lists tasks - must NOT see User A's task
    tasks_b = client.get("/api/v1/tasks", headers=user_b_headers).json()["items"]
    assert not any(t["title"] == "User A Private Study" for t in tasks_b)
