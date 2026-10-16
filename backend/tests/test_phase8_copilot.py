"""Comprehensive test suite for Phase 8: Mentor AI Educational Copilot, Schedule Intelligence & Voice Assistant."""

import uuid
import zoneinfo
from datetime import UTC, date, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from unittest.mock import AsyncMock, patch

from app.core.config import settings
from app.db.base import Base
from app.db.models.calendar import CalendarEvent
from app.db.models.notification import Notification
from app.db.models.profile import Profile, UserPreferences
from app.db.models.schedule import Schedule, ScheduleBlock
from app.db.models.task import Task
from app.main import app
from app.schemas.copilot import (
    CopilotActionConfirmRequest,
    CopilotMessageRequest,
)
from app.services.copilot.accountability import StudentAccountabilityService
from app.services.copilot.learning import (
    count_code_block_lines,
    enforce_code_line_limits,
    is_complete_project_request,
)
from app.services.copilot.search import EducationalSearchService
from app.services.copilot.service import CopilotService
from app.services.copilot.tools import get_schedule_for_date, get_today_schedule
from app.services.gmail.models import (
    GmailMessageSummary,
    GmailMessagesPageResponse,
    GmailStatusResponse,

)
from app.services.gmail.service import GmailService



@pytest.fixture
async def test_session():
    """In-memory SQLite async database engine for isolated Copilot testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_maker() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_today_schedule_retrieval_and_chronology(test_session: AsyncSession):
    """Verify that Copilot retrieves actual schedule items chronologically and distinguishes categories."""
    user_id = uuid.uuid4()
    profile = Profile(id=user_id, email="student@mentor.ai", full_name="Alfi Student", timezone="Asia/Dhaka")
    test_session.add(profile)

    dhaka_tz = zoneinfo.ZoneInfo("Asia/Dhaka")
    now_dhaka = datetime.now(UTC).astimezone(dhaka_tz)
    today = now_dhaka.date()

    # Create Schedule container
    schedule = Schedule(
        id=uuid.uuid4(),
        user_id=user_id,
        schedule_date=today,
    )
    test_session.add(schedule)

    # Create task 1: 09:00 to 10:30 (Scheduled)
    t1_start = datetime.combine(today, datetime.strptime("09:00", "%H:%M").time(), tzinfo=dhaka_tz).astimezone(UTC)
    t1_end = datetime.combine(today, datetime.strptime("10:30", "%H:%M").time(), tzinfo=dhaka_tz).astimezone(UTC)
    task1 = Task(
        id=uuid.uuid4(),
        user_id=user_id,
        title="Mathematics Study Session",
        duration_minutes=90,
        status="in_progress",
        priority="P1",
        scheduled_start=t1_start,
        scheduled_end=t1_end,
    )
    block1 = ScheduleBlock(
        id=uuid.uuid4(),
        schedule_id=schedule.id,
        user_id=user_id,
        task_id=task1.id,
        title="Mathematics Study Session",
        start_time=t1_start,
        end_time=t1_end,
        block_type="task",
    )



    # Create fixed calendar event: 11:30 to 13:00
    ev_start = datetime.combine(today, datetime.strptime("11:30", "%H:%M").time(), tzinfo=dhaka_tz).astimezone(UTC)
    ev_end = datetime.combine(today, datetime.strptime("13:00", "%H:%M").time(), tzinfo=dhaka_tz).astimezone(UTC)
    event1 = CalendarEvent(
        id=uuid.uuid4(),
        user_id=user_id,
        title="Operating Systems Lecture",
        start_time=ev_start,
        end_time=ev_end,
    )

    # Create task with deadline: 20:00 (Unscheduled)
    dl_time = datetime.combine(today, datetime.strptime("20:00", "%H:%M").time(), tzinfo=dhaka_tz).astimezone(UTC)
    task2 = Task(
        id=uuid.uuid4(),
        user_id=user_id,
        title="Algorithms Problem Set",
        deadline=dl_time,
        status="pending",
        priority="P2",
    )


    test_session.add_all([task1, block1, event1, task2])
    await test_session.commit()

    # Invoke tool directly
    summary = await get_today_schedule(test_session, user_id=user_id, user_tz_str="Asia/Dhaka")

    assert summary.total_items == 2  # 1 task block + 1 calendar event
    assert len(summary.deadlines) == 1
    assert summary.deadlines[0]["title"] == "Algorithms Problem Set"

    # Verify chronological ordering (09:00 AM before 11:30 AM)
    assert summary.scheduled_items[0].title == "Mathematics Study Session"
    assert summary.scheduled_items[1].title == "Operating Systems Lecture"
    assert summary.scheduled_items[0].raw_start < summary.scheduled_items[1].raw_start


@pytest.mark.asyncio
async def test_copilot_service_schedule_message(test_session: AsyncSession):
    """Test full CopilotService processing for 'Hey Mentor, give me today's schedule'."""
    user_id = uuid.uuid4()
    profile = Profile(id=user_id, email="user@mentor.ai", full_name="Tanvir", timezone="Asia/Dhaka")
    test_session.add(profile)
    await test_session.commit()

    req = CopilotMessageRequest(
        message="Hey Mentor, give me today's schedule",
        client_timezone="Asia/Dhaka",
    )
    res = await CopilotService.process_message(db=test_session, user_id=user_id, req=req)

    assert res.intent == "schedule_inquiry"
    assert res.schedule_summary is not None
    assert res.navigation is not None
    assert res.navigation.route == "/calendar"
    assert "schedule" in res.reply.lower()


@pytest.mark.asyncio
async def test_educational_search_math101():
    """Verify educational search returns verified resources with real URLs for Math 101."""
    query = "Mentor, Math 101 er ekta bhalo course video suggest koro"
    assert EducationalSearchService.is_educational_query(query) is True

    resources, topic = EducationalSearchService.search_educational_resources(query)
    assert len(resources) >= 2
    assert any("MIT OpenCourseWare" in r.platform for r in resources)
    assert any("Khan Academy" in r.platform for r in resources)
    for r in resources:
        assert r.url.startswith("https://")
        assert len(r.why_recommended) > 10


@pytest.mark.asyncio
async def test_educational_search_dfa():
    """Verify educational search for DFA returns Theory of Computation tutorials."""
    query = "Find a video explaining DFA"
    assert EducationalSearchService.is_educational_query(query) is True

    resources, topic = EducationalSearchService.search_educational_resources(query)
    assert len(resources) >= 2
    assert any("Neso Academy" in r.platform for r in resources)
    assert any("Automata" in r.topic for r in resources)


@pytest.mark.asyncio
async def test_non_educational_search_rejection():
    """Verify that commercial / non-academic queries are identified as non-educational."""
    assert EducationalSearchService.is_educational_query("Where can I buy cheap sneakers?") is False
    assert EducationalSearchService.is_educational_query("Book flight tickets to Dubai") is False


@pytest.mark.asyncio
async def test_programming_education_100_line_limit():
    """Verify that code examples never exceed 100 lines and are bounded strictly."""
    # Generate a dummy 120-line code block
    dummy_code_lines = [f"x_{i} = {i} * 2" for i in range(120)]
    markdown_text = "Here is an implementation:\n```python\n" + "\n".join(dummy_code_lines) + "\n```\nHope this helps!"

    processed, max_observed = enforce_code_line_limits(markdown_text)
    assert max_observed == 120

    # Ensure processed block contains <= 100 code lines plus note
    counts = count_code_block_lines(processed)
    assert len(counts) == 1
    assert counts[0] <= 103  # 100 code lines + note lines


@pytest.mark.asyncio
async def test_complete_project_request_detection():
    """Verify that requests to build entire projects are detected and redirected to a roadmap."""
    assert is_complete_project_request("Build me a complete full-stack SaaS application") is True
    assert is_complete_project_request("Write me a complete app clone") is True
    assert is_complete_project_request("Explain how binary search works") is False


@pytest.mark.asyncio
async def test_student_accountability_missed_session_detection(test_session: AsyncSession):
    """Verify that ended scheduled sessions with incomplete tasks create missed_session notifications."""
    user_id = uuid.uuid4()
    profile = Profile(id=user_id, email="student@mentor.ai", full_name="Alfi", timezone="Asia/Dhaka")
    test_session.add(profile)

    now_utc = datetime.now(UTC)
    # A block that ended 30 minutes ago
    ended_start = now_utc - timedelta(hours=1, minutes=30)
    ended_end = now_utc - timedelta(minutes=30)

    task = Task(
        id=uuid.uuid4(),
        user_id=user_id,
        title="Physics Problem Set 3",
        status="in_progress",  # Incomplete!
        is_archived=False,
    )
    schedule = Schedule(
        id=uuid.uuid4(),
        user_id=user_id,
        schedule_date=ended_start.date(),
    )
    test_session.add(schedule)

    block = ScheduleBlock(
        id=uuid.uuid4(),
        schedule_id=schedule.id,
        user_id=user_id,
        task_id=task.id,
        title="Physics Problem Set 3",
        start_time=ended_start,
        end_time=ended_end,
        block_type="task",
    )
    test_session.add_all([task, block])
    await test_session.commit()

    created_notifs = await StudentAccountabilityService.evaluate_missed_sessions(
        db=test_session, user_id=user_id
    )

    assert len(created_notifs) == 1
    assert created_notifs[0].notification_type == "missed_session"
    assert "Physics Problem Set 3" in created_notifs[0].message
    assert "still incomplete" in created_notifs[0].message

    # Running a second time should deduplicate and create 0 new notifications
    second_pass = await StudentAccountabilityService.evaluate_missed_sessions(
        db=test_session, user_id=user_id
    )
    assert len(second_pass) == 0


@pytest.mark.asyncio
async def test_completed_task_does_not_trigger_missed_session(test_session: AsyncSession):
    """Verify that tasks marked 'completed' do not trigger missed session alerts."""
    user_id = uuid.uuid4()
    profile = Profile(id=user_id, email="grad@mentor.ai", full_name="Graduate", timezone="Asia/Dhaka")
    test_session.add(profile)

    now_utc = datetime.now(UTC)
    task = Task(
        id=uuid.uuid4(),
        user_id=user_id,
        title="Submit Thesis Draft",
        status="completed",  # Completed!
        is_archived=False,
    )
    schedule = Schedule(
        id=uuid.uuid4(),
        user_id=user_id,
        schedule_date=now_utc.date(),
    )
    test_session.add(schedule)

    block = ScheduleBlock(
        id=uuid.uuid4(),
        schedule_id=schedule.id,
        user_id=user_id,
        task_id=task.id,
        title="Submit Thesis Draft",
        start_time=now_utc - timedelta(hours=2),
        end_time=now_utc - timedelta(hours=1),
        block_type="task",
    )
    test_session.add_all([task, block])
    await test_session.commit()

    created = await StudentAccountabilityService.evaluate_missed_sessions(
        db=test_session, user_id=user_id
    )
    assert len(created) == 0


@pytest.mark.asyncio
async def test_email_copilot_safety_confirmation_boundary(test_session: AsyncSession):
    """Verify that Copilot prepares an email preview with confirmation required and does not send without approval."""
    user_id = uuid.uuid4()
    profile = Profile(id=user_id, email="me@mentor.ai", full_name="Student Me")
    test_session.add(profile)
    await test_session.commit()

    # Mock connected Gmail status and matching message from professor
    mock_status = GmailStatusResponse(
        is_connected=True,
        configured=True,
        status_label="connected",
        account_email="me@mentor.ai",
        is_stale=False,
        recent_inbox_count=1,
    )

    mock_messages_list = GmailMessagesPageResponse(
        messages=[
            GmailMessageSummary(
                id="msg_123",
                thread_id="th_123",
                sender="Prof. David Jerison <david@mit.edu>",
                subject="Math 101 Assignment 4 Submission",
                snippet="Please submit your homework solutions before the deadline.",
                received_at=datetime.now(UTC),
                is_unread=True,
            )
        ],
        total_estimate=1,
    )

    with patch.object(GmailService, "get_status", new_callable=AsyncMock, return_value=mock_status), \
         patch.object(GmailService, "list_messages", new_callable=AsyncMock, return_value=mock_messages_list):
        req = CopilotMessageRequest(
            message="Reply to my course instructor that I will submit the assignment tomorrow",
            client_timezone="Asia/Dhaka",
        )
        res = await CopilotService.process_message(db=test_session, user_id=user_id, req=req)

        assert res.intent == "email_reply"
        assert res.email_draft is not None
        # Must require explicit confirmation before sending
        assert res.email_draft.requires_confirmation is True
        assert res.email_draft.status == "draft_ready"
        assert "david@mit.edu" in res.email_draft.recipient_email
        assert "Re: Math 101 Assignment 4 Submission" in res.email_draft.subject
        assert "tomorrow" in res.email_draft.body
        # Must not be sent prematurely
        assert res.email_draft.status != "sent"

