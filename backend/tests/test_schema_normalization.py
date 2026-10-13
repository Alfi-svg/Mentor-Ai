"""Tests for Task and Planner schema pre-validation and alias normalization."""

from datetime import UTC, datetime

from app.schemas.planner import PlanConfirmRequest
from app.schemas.task import TaskCreateRequest


def test_task_create_request_duration_mapping():
    """Verify that estimated_duration_minutes is automatically mapped to duration_minutes."""
    payload = {
        "title": "Build Authentication Service",
        "estimated_duration_minutes": 120,
    }
    task = TaskCreateRequest(**payload)
    assert task.duration_minutes == 120
    assert task.energy_level == "medium"
    assert task.priority == "P3"
    assert task.deadline is None


def test_task_create_request_deadline_empty_string():
    """Verify that empty string deadline is normalized to None."""
    payload = {
        "title": "Write Unit Tests",
        "deadline": "",
    }
    task = TaskCreateRequest(**payload)
    assert task.deadline is None


def test_task_create_request_energy_level_and_priority_normalization():
    """Verify null or alias energy_level and priority normalization."""
    payload = {
        "title": "Code Review",
        "energy_level": None,
        "priority": "p1",
    }
    task = TaskCreateRequest(**payload)
    assert task.energy_level == "medium"
    assert task.priority == "P1"

    # Test word priority
    payload2 = {
        "title": "Urgent Security Patch",
        "priority": "HIGH",
    }
    task2 = TaskCreateRequest(**payload2)
    assert task2.priority == "P1"


def test_plan_confirm_request_with_planner_tasks():
    """Verify that PlanConfirmRequest correctly validates tasks coming from planner UI."""
    payload = {
        "target_date": "2026-10-15",
        "tasks": [
            {
                "title": "Task 1",
                "estimated_duration_minutes": 90,
                "deadline": None,
                "energy_level": None,
            },
            {
                "title": "Task 2",
                "duration_minutes": 45,
                "priority": "P2",
            },
        ],
        "persist_tasks": True,
        "generate_schedule": True,
    }
    req = PlanConfirmRequest(**payload)
    assert len(req.tasks) == 2
    assert req.tasks[0].duration_minutes == 90
    assert req.tasks[0].energy_level == "medium"
    assert req.tasks[1].duration_minutes == 45
    assert req.tasks[1].priority == "P2"
