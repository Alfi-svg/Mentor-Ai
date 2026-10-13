"""Pytest fixtures for backend tests with database isolation."""

import os
import sys
import uuid
from collections.abc import AsyncGenerator, Generator
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Ensure backend directory is in sys.path
backend_dir = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.core.security import create_jwt_token  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402

TEST_DB_FILE = "./test_mentor_ai_fixture.db"
TEST_DB_URL = f"sqlite+aiosqlite:///{TEST_DB_FILE}"

sync_engine = create_engine(
    f"sqlite:///{TEST_DB_FILE}",
    echo=False,
    connect_args={"check_same_thread": False},
)

test_engine = create_async_engine(
    TEST_DB_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)
TestSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

import app.db.session as db_session_module  # noqa: E402

db_session_module._session_factory = TestSessionLocal
db_session_module._engine = test_engine


@pytest.fixture(scope="session", autouse=True)
def prepare_database() -> Generator[None, None, None]:
    """Create all tables before test session and drop after."""
    Base.metadata.drop_all(sync_engine)
    Base.metadata.create_all(sync_engine)
    yield
    Base.metadata.drop_all(sync_engine)
    sync_engine.dispose()
    if os.path.exists(TEST_DB_FILE):
        try:
            os.remove(TEST_DB_FILE)
        except OSError:
            pass


async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    """Override get_db dependency for tests."""
    async with TestSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@pytest.fixture(scope="session")
def client() -> Generator[TestClient, None, None]:
    """TestClient fixture with overridden DB dependency."""
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yields an isolated async db session for direct model manipulation in tests."""
    async with TestSessionLocal() as session:
        yield session


# -----------------------------------------------------------------------------
# User Personas for Multi-Tenant Isolation Testing
# -----------------------------------------------------------------------------
USER_A_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
USER_A_EMAIL = "alex.student@university.edu"

USER_B_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
USER_B_EMAIL = "priya.lead@company.com"


@pytest.fixture
def user_a_token() -> str:
    """Valid JWT token for User A."""
    return create_jwt_token(user_id=USER_A_ID, email=USER_A_EMAIL)


@pytest.fixture
def user_b_token() -> str:
    """Valid JWT token for User B."""
    return create_jwt_token(user_id=USER_B_ID, email=USER_B_EMAIL)


@pytest.fixture
def user_a_headers(user_a_token: str) -> dict[str, str]:
    """Authorization headers for User A."""
    return {"Authorization": f"Bearer {user_a_token}"}


@pytest.fixture
def user_b_headers(user_b_token: str) -> dict[str, str]:
    """Authorization headers for User B."""
    return {"Authorization": f"Bearer {user_b_token}"}


from sqlalchemy import select  # noqa: E402
from app.db.models.profile import Profile, UserPreferences  # noqa: E402


@pytest_asyncio.fixture(autouse=True)
async def seed_test_personas(db_session: AsyncSession) -> None:
    """Ensure User A and User B personas have profiles and preferences in tests."""
    res_a = await db_session.execute(select(Profile).where(Profile.id == USER_A_ID))
    if not res_a.scalar_one_or_none():
        db_session.add(
            Profile(
                id=USER_A_ID,
                email=USER_A_EMAIL,
                full_name="Alex Student",
                timezone="America/New_York",
            )
        )
        db_session.add(
            UserPreferences(
                user_id=USER_A_ID,
                work_start_time="09:00:00",
                work_end_time="18:00:00",
                buffer_minutes=15,
                default_task_duration=45,
                max_focus_hours_per_day=8,
                available_days=[1, 2, 3, 4, 5],
                auto_schedule_breaks=True,
            )
        )

    res_b = await db_session.execute(select(Profile).where(Profile.id == USER_B_ID))
    if not res_b.scalar_one_or_none():
        db_session.add(
            Profile(
                id=USER_B_ID,
                email=USER_B_EMAIL,
                full_name="Priya Lead",
                timezone="America/New_York",
            )
        )
        db_session.add(
            UserPreferences(
                user_id=USER_B_ID,
                work_start_time="09:00:00",
                work_end_time="18:00:00",
                buffer_minutes=15,
                default_task_duration=45,
                max_focus_hours_per_day=8,
                available_days=[1, 2, 3, 4, 5],
                auto_schedule_breaks=True,
            )
        )
    await db_session.commit()
