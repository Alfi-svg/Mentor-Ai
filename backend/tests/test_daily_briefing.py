"""Comprehensive unit and integration tests for Mentor AI Copilot Proactive Daily Briefing."""

import uuid
import zoneinfo
from datetime import UTC, datetime, time, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models.calendar import CalendarEvent
from app.db.models.profile import Profile
from app.db.models.schedule import Schedule, ScheduleBlock
from app.db.models.task import Task
from app.schemas.copilot import CopilotMessageRequest
from app.services.copilot.service import CopilotService
from app.services.copilot.tools import get_daily_briefing
from app.services.copilot_agent import CopilotAgent


@pytest.fixture
async def test_session():
    """In-memory SQLite async database engine for isolated Daily Briefing testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_maker() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_daily_briefing_all_clear(test_session: AsyncSession):
    """Verify Daily Briefing produces an honest 'all_clear' state when no tasks or events exist."""
    user_id = uuid.uuid4()
    profile = Profile(id=user_id, email=f"user_{user_id.hex[:8]}@example.com", timezone="Asia/Dhaka")
    test_session.add(profile)
    await test_session.commit()

    briefing = await get_daily_briefing(db=test_session, user_id=user_id, user_tz_str="Asia/Dhaka")

    assert "briefing_payload" in briefing
    assert "formatted_markdown" in briefing
    assert "spoken_summary" in briefing
    assert "recommended_focus" in briefing

    payload = briefing["briefing_payload"]
    assert payload["overdue_count"] == 0
    assert payload["scheduled_items_count"] == 0
    assert payload["upcoming_deadlines_count"] == 0
    assert payload["recommended_focus"]["action_type"] == "all_clear"
    assert "All caught up" in payload["recommended_focus"]["title"]
    assert "Daily Briefing" in briefing["formatted_markdown"]
    assert len(briefing["spoken_summary"]) > 20


@pytest.mark.asyncio
async def test_daily_briefing_prioritizes_p1_overdue_task(test_session: AsyncSession):
    """Verify Daily Briefing deterministically selects critical P1 overdue tasks as recommended focus."""
    user_id = uuid.uuid4()
    now_utc = datetime.now(UTC)

    # Add Profile
    test_session.add(Profile(id=user_id, email=f"user_{user_id.hex[:8]}@example.com", timezone="UTC"))

    # Overdue P1 task
    t_overdue = Task(
        id=uuid.uuid4(),
        user_id=user_id,
        title="Urgent Thesis Chapter Submission",
        priority="P1",
        deadline=now_utc - timedelta(hours=4),
        status="pending",
    )
    # Upcoming P2 task
    t_upcoming = Task(
        id=uuid.uuid4(),
        user_id=user_id,
        title="Review Lecture Slides",
        priority="P2",
        deadline=now_utc + timedelta(hours=24),
        status="pending",
    )
    test_session.add_all([t_overdue, t_upcoming])
    await test_session.commit()

    briefing = await get_daily_briefing(db=test_session, user_id=user_id, user_tz_str="UTC")
    rec = briefing["recommended_focus"]

    assert rec["action_type"] == "overdue"
    assert rec["priority"] == "P1"
    assert rec["title"] == "Urgent Thesis Chapter Submission"
    assert "overdue" in rec["reason"].lower()
    assert briefing["overdue_count"] == 1


@pytest.mark.asyncio
async def test_daily_briefing_prioritizes_scheduled_block_when_no_overdue(test_session: AsyncSession):
    """Verify Daily Briefing recommends scheduled study block when there are no overdue tasks."""
    user_id = uuid.uuid4()
    tz = zoneinfo.ZoneInfo("Asia/Dhaka")
    now_loc = datetime.now(UTC).astimezone(tz)
    today = now_loc.date()

    test_session.add(Profile(id=user_id, email=f"user_{user_id.hex[:8]}@example.com", timezone="Asia/Dhaka"))

    # Create task and scheduled block today
    task_id = uuid.uuid4()
    t = Task(
        id=task_id,
        user_id=user_id,
        title="Data Structures Lab",
        priority="P2",
        status="in_progress",
    )
    test_session.add(t)

    sched_start = datetime.combine(today, time(14, 0, 0), tzinfo=tz).astimezone(UTC)
    sched_end = datetime.combine(today, time(16, 0, 0), tzinfo=tz).astimezone(UTC)

    sched_id = uuid.uuid4()
    schedule = Schedule(id=sched_id, user_id=user_id, schedule_date=today)
    test_session.add(schedule)

    block = ScheduleBlock(
        id=uuid.uuid4(),
        schedule_id=sched_id,
        user_id=user_id,
        task_id=task_id,
        title="Data Structures Lab Focus",
        start_time=sched_start,
        end_time=sched_end,
        block_type="task",
        is_completed=False,
    )
    test_session.add(block)
    await test_session.commit()

    briefing = await get_daily_briefing(db=test_session, user_id=user_id, user_tz_str="Asia/Dhaka")
    rec = briefing["recommended_focus"]

    assert rec["action_type"] == "scheduled_block"
    assert "Data Structures Lab Focus" in rec["title"]
    assert "dedicated study session" in rec["reason"].lower()
    assert briefing["scheduled_items_count"] == 1


@pytest.mark.asyncio
async def test_daily_briefing_upcoming_deadline_recommendation(test_session: AsyncSession):
    """Verify Daily Briefing recommends imminent deadline when no overdue or scheduled blocks exist."""
    user_id = uuid.uuid4()
    now_utc = datetime.now(UTC)

    test_session.add(Profile(id=user_id, email=f"user_{user_id.hex[:8]}@example.com", timezone="UTC"))

    # Task due in 24 hours
    t = Task(
        id=uuid.uuid4(),
        user_id=user_id,
        title="Math Assignment 3",
        priority="P1",
        deadline=now_utc + timedelta(hours=24),
        status="pending",
    )
    test_session.add(t)
    await test_session.commit()

    briefing = await get_daily_briefing(db=test_session, user_id=user_id, user_tz_str="UTC")
    rec = briefing["recommended_focus"]

    assert rec["action_type"] == "upcoming_deadline"
    assert rec["title"] == "Math Assignment 3"
    assert rec["priority"] == "P1"
    assert "approaching" in rec["reason"].lower()
    assert briefing["upcoming_deadlines_count"] == 1


@pytest.mark.asyncio
async def test_daily_briefing_graceful_offline_integrations(test_session: AsyncSession):
    """Verify Daily Briefing truthfully reports disconnected Calendar and Gmail without hallucinating."""
    user_id = uuid.uuid4()
    test_session.add(Profile(id=user_id, email=f"user_{user_id.hex[:8]}@example.com", timezone="UTC"))
    await test_session.commit()

    briefing = await get_daily_briefing(db=test_session, user_id=user_id, user_tz_str="UTC")

    assert briefing["gmail_status"] == "disconnected"
    assert briefing["calendar_status"] == "disconnected"
    assert briefing["unread_emails_count"] == 0
    assert "Google Calendar is not connected" in briefing["formatted_markdown"]
    assert "Gmail is not connected" in briefing["formatted_markdown"]


@pytest.mark.asyncio
async def test_copilot_service_daily_briefing_intent(test_session: AsyncSession):
    """Verify CopilotService classifies daily briefing requests and returns full briefing envelope."""
    user_id = uuid.uuid4()
    test_session.add(Profile(id=user_id, email=f"user_{user_id.hex[:8]}@example.com", timezone="Asia/Dhaka"))
    await test_session.commit()

    # Query 1: "Brief me on my day"
    req1 = CopilotMessageRequest(message="Brief me on my day", input_mode="text")
    res1 = await CopilotService.process_message(db=test_session, user_id=user_id, req=req1)

    assert res1.intent == "daily_briefing"
    assert res1.daily_briefing is not None
    assert res1.daily_briefing.timezone == "Asia/Dhaka"
    assert res1.navigation is not None
    assert res1.navigation.route == "/planner"
    assert "Daily Briefing" in res1.reply
    assert res1.spoken_reply is not None

    # Query 2: "What should I focus on first?"
    req2 = CopilotMessageRequest(message="What should I focus on first?", input_mode="text")
    res2 = await CopilotService.process_message(db=test_session, user_id=user_id, req=req2)
    assert res2.intent == "daily_briefing"
    assert res2.daily_briefing is not None


@pytest.mark.asyncio
async def test_copilot_agent_execute_single_tool_daily_briefing(test_session: AsyncSession):
    """Verify CopilotAgent._execute_single_tool dispatches get_daily_briefing and collects state."""
    user_id = uuid.uuid4()
    test_session.add(Profile(id=user_id, email=f"user_{user_id.hex[:8]}@example.com", timezone="UTC"))
    await test_session.commit()

    context_state = {
        "schedule_summary": None,
        "resources": None,
        "email_draft": None,
        "navigation": None,
        "accountability_data": None,
        "approval_id": None,
        "daily_briefing": None,
    }

    tool_output = await CopilotAgent._execute_single_tool(
        db=test_session,
        user_id=user_id,
        user_tz="UTC",
        now_loc=datetime.now(UTC),
        fn_name="get_daily_briefing",
        fn_args={},
        context_state=context_state,
    )

    assert "briefing_payload" in tool_output
    assert context_state["daily_briefing"] is not None
    assert context_state["schedule_summary"] is not None
    assert context_state["navigation"] is not None
    assert context_state["navigation"].route == "/planner"
