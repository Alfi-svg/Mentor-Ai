"""Comprehensive automated tests for Mentor AI task management CRUD, validation,

lifecycle state transitions, filtering, pagination, and multi-tenant isolation.
"""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from tests.backend.conftest import USER_A_ID, USER_B_ID


def test_unauthenticated_tasks_access_rejected(client: TestClient) -> None:
    """Verify that all task endpoints strictly reject unauthenticated requests with 401."""
    # 1. List
    res = client.get("/api/v1/tasks")
    assert res.status_code == 401
    assert res.json()["error_code"] == "UNAUTHORIZED"

    # 2. Create
    res = client.post("/api/v1/tasks", json={"title": "Unauthorized Task"})
    assert res.status_code == 401

    # 3. Get by ID
    res = client.get(f"/api/v1/tasks/{uuid.uuid4()}")
    assert res.status_code == 401

    # 4. Update
    res = client.patch(f"/api/v1/tasks/{uuid.uuid4()}", json={"title": "Hacked"})
    assert res.status_code == 401

    # 5. Delete
    res = client.delete(f"/api/v1/tasks/{uuid.uuid4()}")
    assert res.status_code == 401


def test_create_task_minimal_attributes(
    client: TestClient, user_a_headers: dict[str, str]
) -> None:
    """Verify creating a task with only required attributes applies production defaults."""
    payload = {"title": "Submit CS301 Problem Set 1"}
    res = client.post("/api/v1/tasks", json=payload, headers=user_a_headers)
    assert res.status_code == 201

    data = res.json()
    assert data["title"] == "Submit CS301 Problem Set 1"
    assert data["user_id"] == str(USER_A_ID)
    assert data["priority"] == "P3"
    assert data["duration_minutes"] == 45
    assert data["status"] == "pending"
    assert data["energy_level"] == "medium"
    assert data["tags"] == []
    assert data["constraints"] == {}
    assert data["is_archived"] is False
    assert data["deadline"] is None
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data


def test_create_task_full_attributes_and_utc_normalization(
    client: TestClient, user_a_headers: dict[str, str]
) -> None:
    """Verify creating a task with full attributes, tags, constraints, and timezone normalization."""
    # Deadline with +02:00 timezone offset (18:00 +02:00 = 16:00 UTC)
    deadline_input = "2026-10-20T18:00:00+02:00"
    payload = {
        "title": "   Finalize Compiler Optimization Report   ",
        "description": "LLVM pass profiling and benchmark results",
        "priority": "P1",
        "duration_minutes": 120,
        "deadline": deadline_input,
        "energy_level": "high",
        "tags": [
            "CS405",
            "llvm",
            "COMPILER",
            "  CS405  ",
        ],  # Should be deduplicated & lowercased
        "constraints": {
            "earliest_start": "09:00",
            "latest_end": "17:00",
            "preferred_time_of_day": "morning",
        },
    }
    res = client.post("/api/v1/tasks", json=payload, headers=user_a_headers)
    assert res.status_code == 201

    data = res.json()
    assert data["title"] == "Finalize Compiler Optimization Report"  # Trimmed
    assert data["priority"] == "P1"
    assert data["duration_minutes"] == 120
    assert data["energy_level"] == "high"
    assert data["tags"] == ["cs405", "llvm", "compiler"]  # Deduplicated and lowercased
    assert data["constraints"]["preferred_time_of_day"] == "morning"

    # Deadline normalized to UTC (16:00:00Z)
    stored_deadline = datetime.fromisoformat(data["deadline"])
    assert stored_deadline.hour == 16
    assert stored_deadline.tzinfo is not None


def test_create_task_validation_errors(
    client: TestClient, user_a_headers: dict[str, str]
) -> None:
    """Verify input validation rules return HTTP 422 with structured validation issues."""
    # 1. Empty title after whitespace trimming
    res = client.post("/api/v1/tasks", json={"title": "   "}, headers=user_a_headers)
    assert res.status_code == 422
    assert res.json()["error_code"] == "VALIDATION_ERROR"

    # 2. Duration less than 1 minute
    res = client.post(
        "/api/v1/tasks",
        json={"title": "Fast task", "duration_minutes": 0},
        headers=user_a_headers,
    )
    assert res.status_code == 422

    # 3. Duration greater than 720 minutes (12 hours)
    res = client.post(
        "/api/v1/tasks",
        json={"title": "Too long task", "duration_minutes": 721},
        headers=user_a_headers,
    )
    assert res.status_code == 422

    # 4. Invalid priority
    res = client.post(
        "/api/v1/tasks",
        json={"title": "Invalid Priority Task", "priority": "P5"},
        headers=user_a_headers,
    )
    assert res.status_code == 422

    # 5. Invalid energy level
    res = client.post(
        "/api/v1/tasks",
        json={"title": "Invalid Energy Task", "energy_level": "extreme"},
        headers=user_a_headers,
    )
    assert res.status_code == 422


def test_get_single_task_and_missing_task_404(
    client: TestClient, user_a_headers: dict[str, str]
) -> None:
    """Verify retrieving an existing task succeeds and non-existent task returns 404."""
    # Create task
    create_res = client.post(
        "/api/v1/tasks",
        json={"title": "Review Distributed Systems paper"},
        headers=user_a_headers,
    )
    task_id = create_res.json()["id"]

    # Retrieve task
    get_res = client.get(f"/api/v1/tasks/{task_id}", headers=user_a_headers)
    assert get_res.status_code == 200
    assert get_res.json()["id"] == task_id
    assert get_res.json()["title"] == "Review Distributed Systems paper"

    # Non-existent task ID
    missing_id = uuid.uuid4()
    not_found_res = client.get(f"/api/v1/tasks/{missing_id}", headers=user_a_headers)
    assert not_found_res.status_code == 404
    assert not_found_res.json()["error_code"] == "NOT_FOUND"


def test_multi_tenant_task_isolation(
    client: TestClient,
    user_a_headers: dict[str, str],
    user_b_headers: dict[str, str],
) -> None:
    """Verify that User A cannot read, update, or delete User B's tasks under any circumstance."""
    # 1. User B creates a private task
    create_res = client.post(
        "/api/v1/tasks",
        json={
            "title": "User B Confidential Client Meeting Preparation",
            "priority": "P1",
        },
        headers=user_b_headers,
    )
    assert create_res.status_code == 201
    user_b_task_id = create_res.json()["id"]
    assert create_res.json()["user_id"] == str(USER_B_ID)

    # 2. User A attempts to GET User B's task -> Must return 404 (not 403, preventing enumeration)
    get_res = client.get(f"/api/v1/tasks/{user_b_task_id}", headers=user_a_headers)
    assert get_res.status_code == 404
    assert get_res.json()["error_code"] == "NOT_FOUND"

    # 3. User A attempts to PATCH User B's task -> Must return 404
    patch_res = client.patch(
        f"/api/v1/tasks/{user_b_task_id}",
        json={"title": "Malicious Tampering by User A"},
        headers=user_a_headers,
    )
    assert patch_res.status_code == 404

    # 4. User A attempts to complete User B's task -> Must return 404
    complete_res = client.post(
        f"/api/v1/tasks/{user_b_task_id}/complete",
        headers=user_a_headers,
    )
    assert complete_res.status_code == 404

    # 5. User A attempts to DELETE User B's task -> Must return 404
    delete_res = client.delete(
        f"/api/v1/tasks/{user_b_task_id}", headers=user_a_headers
    )
    assert delete_res.status_code == 404

    # 6. Verify User B's task remains completely unaltered
    verify_res = client.get(f"/api/v1/tasks/{user_b_task_id}", headers=user_b_headers)
    assert verify_res.status_code == 200
    assert (
        verify_res.json()["title"] == "User B Confidential Client Meeting Preparation"
    )


def test_partial_update_task(
    client: TestClient, user_a_headers: dict[str, str]
) -> None:
    """Verify partial task updates (title, priority, duration, constraints)."""
    # Create task
    create_res = client.post(
        "/api/v1/tasks",
        json={"title": "Initial Task Title", "duration_minutes": 30, "priority": "P4"},
        headers=user_a_headers,
    )
    task_id = create_res.json()["id"]

    # Update title and priority
    patch_res = client.patch(
        f"/api/v1/tasks/{task_id}",
        json={"title": "Updated Task Title", "priority": "P2", "duration_minutes": 60},
        headers=user_a_headers,
    )
    assert patch_res.status_code == 200
    data = patch_res.json()
    assert data["title"] == "Updated Task Title"
    assert data["priority"] == "P2"
    assert data["duration_minutes"] == 60


def test_task_status_state_machine_transitions(
    client: TestClient, user_a_headers: dict[str, str]
) -> None:
    """Verify state machine lifecycle transitions (pending -> in_progress -> completed -> reopened)

    and reject illegal direct transitions (completed -> cancelled).
    """
    create_res = client.post(
        "/api/v1/tasks",
        json={"title": "Write Unit Tests for Architecture"},
        headers=user_a_headers,
    )
    task_id = create_res.json()["id"]
    assert create_res.json()["status"] == "pending"

    # 1. pending -> in_progress (Valid)
    res = client.patch(
        f"/api/v1/tasks/{task_id}",
        json={"status": "in_progress"},
        headers=user_a_headers,
    )
    assert res.status_code == 200
    assert res.json()["status"] == "in_progress"

    # 2. in_progress -> completed (Valid)
    res = client.post(f"/api/v1/tasks/{task_id}/complete", headers=user_a_headers)
    assert res.status_code == 200
    assert res.json()["status"] == "completed"

    # 3. completed -> cancelled (Illegal transition -> Expect 400 INVALID_STATUS_TRANSITION)
    res = client.patch(
        f"/api/v1/tasks/{task_id}", json={"status": "cancelled"}, headers=user_a_headers
    )
    assert res.status_code == 400
    assert res.json()["error_code"] == "INVALID_STATUS_TRANSITION"

    # 4. completed -> pending (Valid Reopen)
    res = client.post(f"/api/v1/tasks/{task_id}/reopen", headers=user_a_headers)
    assert res.status_code == 200
    assert res.json()["status"] == "pending"

    # 5. pending -> cancelled (Valid)
    res = client.patch(
        f"/api/v1/tasks/{task_id}", json={"status": "cancelled"}, headers=user_a_headers
    )
    assert res.status_code == 200
    assert res.json()["status"] == "cancelled"

    # 6. cancelled -> completed (Illegal transition -> Expect 400)
    res = client.patch(
        f"/api/v1/tasks/{task_id}", json={"status": "completed"}, headers=user_a_headers
    )
    assert res.status_code == 400
    assert res.json()["error_code"] == "INVALID_STATUS_TRANSITION"


def test_task_archive_and_unarchive(
    client: TestClient, user_a_headers: dict[str, str]
) -> None:
    """Verify archiving hides tasks from active list by default, but allows filtering."""
    create_res = client.post(
        "/api/v1/tasks",
        json={"title": "Archivable Task Example"},
        headers=user_a_headers,
    )
    task_id = create_res.json()["id"]

    # Archive task
    arch_res = client.post(f"/api/v1/tasks/{task_id}/archive", headers=user_a_headers)
    assert arch_res.status_code == 200
    assert arch_res.json()["is_archived"] is True

    # Active list (is_archived=False default) should NOT contain this task
    list_active = client.get("/api/v1/tasks", headers=user_a_headers)
    active_ids = [t["id"] for t in list_active.json()["items"]]
    assert task_id not in active_ids

    # Archived list (is_archived=True) SHOULD contain this task
    list_archived = client.get("/api/v1/tasks?is_archived=true", headers=user_a_headers)
    archived_ids = [t["id"] for t in list_archived.json()["items"]]
    assert task_id in archived_ids

    # Unarchive task
    unarch_res = client.post(
        f"/api/v1/tasks/{task_id}/unarchive", headers=user_a_headers
    )
    assert unarch_res.status_code == 200
    assert unarch_res.json()["is_archived"] is False


def test_list_tasks_filtering_sorting_and_pagination(
    client: TestClient, user_a_headers: dict[str, str]
) -> None:
    """Verify rich query filtering by priority, energy level, search term, sorting, and pagination."""
    # Create distinctive tasks for User A
    now = datetime.now(UTC)
    t1 = client.post(
        "/api/v1/tasks",
        json={
            "title": "Quantum Computing Assignment",
            "description": "Grover search algorithm proof",
            "priority": "P1",
            "energy_level": "high",
            "duration_minutes": 90,
            "deadline": (now + timedelta(days=2)).isoformat(),
        },
        headers=user_a_headers,
    ).json()

    t2 = client.post(
        "/api/v1/tasks",
        json={
            "title": "Algorithms Homework 3",
            "description": "Dynamic programming longest path",
            "priority": "P2",
            "energy_level": "high",
            "duration_minutes": 60,
            "deadline": (now + timedelta(days=4)).isoformat(),
        },
        headers=user_a_headers,
    ).json()

    t3 = client.post(
        "/api/v1/tasks",
        json={
            "title": "Email Professor regarding Office Hours",
            "description": "Ask about project submission deadline extension",
            "priority": "P4",
            "energy_level": "low",
            "duration_minutes": 15,
            "deadline": None,
        },
        headers=user_a_headers,
    ).json()

    # 1. Filter by priority P1
    p1_res = client.get("/api/v1/tasks?priority=P1", headers=user_a_headers)
    assert p1_res.status_code == 200
    p1_items = p1_res.json()["items"]
    assert any(t["id"] == t1["id"] for t in p1_items)
    assert not any(t["id"] == t2["id"] for t in p1_items)
    assert not any(t["id"] == t3["id"] for t in p1_items)

    # Filter by priority P2
    p2_res = client.get("/api/v1/tasks?priority=P2", headers=user_a_headers)
    assert p2_res.status_code == 200
    assert any(t["id"] == t2["id"] for t in p2_res.json()["items"])

    # 2. Filter by energy level low
    low_res = client.get("/api/v1/tasks?energy_level=low", headers=user_a_headers)
    assert low_res.status_code == 200
    assert any(t["id"] == t3["id"] for t in low_res.json()["items"])

    # 3. Search query "Grover"
    search_res = client.get("/api/v1/tasks?search=Grover", headers=user_a_headers)
    assert search_res.status_code == 200
    search_items = search_res.json()["items"]
    assert len(search_items) >= 1
    assert any(t["id"] == t1["id"] for t in search_items)

    # 4. Sorting by duration_minutes desc
    sort_res = client.get(
        "/api/v1/tasks?sort_by=duration_minutes&sort_order=desc", headers=user_a_headers
    )
    assert sort_res.status_code == 200
    durations = [t["duration_minutes"] for t in sort_res.json()["items"]]
    assert durations == sorted(durations, reverse=True)

    # 5. Pagination with limit and offset
    page1 = client.get("/api/v1/tasks?limit=2&offset=0", headers=user_a_headers).json()
    assert len(page1["items"]) <= 2
    assert page1["limit"] == 2
    assert page1["offset"] == 0
    assert page1["total"] >= 3

    page2 = client.get("/api/v1/tasks?limit=2&offset=2", headers=user_a_headers).json()
    assert page2["offset"] == 2
    # Ensure page1 and page2 do not overlap
    page1_ids = {t["id"] for t in page1["items"]}
    page2_ids = {t["id"] for t in page2["items"]}
    assert page1_ids.isdisjoint(page2_ids)


def test_hard_delete_task(client: TestClient, user_a_headers: dict[str, str]) -> None:
    """Verify task deletion returns 204 No Content and permanently removes task from DB."""
    create_res = client.post(
        "/api/v1/tasks",
        json={"title": "Disposable Task to Delete"},
        headers=user_a_headers,
    )
    task_id = create_res.json()["id"]

    # Delete task
    del_res = client.delete(f"/api/v1/tasks/{task_id}", headers=user_a_headers)
    assert del_res.status_code == 204

    # Subsequent GET returns 404
    get_res = client.get(f"/api/v1/tasks/{task_id}", headers=user_a_headers)
    assert get_res.status_code == 404
    assert get_res.json()["error_code"] == "NOT_FOUND"

    # Second DELETE on same ID returns 404
    del_again_res = client.delete(f"/api/v1/tasks/{task_id}", headers=user_a_headers)
    assert del_again_res.status_code == 404
