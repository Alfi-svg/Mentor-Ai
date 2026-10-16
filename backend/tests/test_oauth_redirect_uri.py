"""Comprehensive test suite for Google Calendar and Gmail OAuth Redirect URI verification,
auto-healing, browser redirects, and error handling.
"""

import urllib.parse
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, settings
from app.core.crypto import generate_oauth_state
from app.db.base import Base
from app.db.models.profile import Profile
from app.db.session import get_db
from app.main import app
from app.services.calendar.google import GoogleCalendarAdapter
from app.services.calendar.mock import MockCalendarAdapter
from app.services.calendar.models import OAuthTokenData
from app.services.calendar.service import CalendarService
from app.services.gmail.google import GoogleGmailAdapter
from app.services.gmail.mock import MockGmailAdapter
from app.services.gmail.service import GmailService
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest.fixture
async def test_db():
    """Create in-memory async SQLite database session."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        # Override FastAPI get_db dependency
        async def override_get_db():
            yield session

        app.dependency_overrides[get_db] = override_get_db
        yield session
        app.dependency_overrides.pop(get_db, None)

    await engine.dispose()


def test_oauth_redirect_uri_assembly_development():
    """In development, defaults remain localhost."""
    s = Settings(ENVIRONMENT="development")
    assert s.GOOGLE_REDIRECT_URI == "http://localhost:8000/api/v1/calendar/callback"
    assert s.GOOGLE_GMAIL_REDIRECT_URI == "http://localhost:8000/api/v1/gmail/callback"
    assert s.FRONTEND_URL == "http://localhost:3000"


def test_oauth_redirect_uri_assembly_production():
    """In production, redirect URIs default to canonical production domain and strip trailing slashes."""
    s = Settings(
        ENVIRONMENT="production",
        GOOGLE_REDIRECT_URI="http://localhost:8000/api/v1/calendar/callback/",
        GOOGLE_GMAIL_REDIRECT_URI="http://localhost:8000/api/v1/gmail/callback/",
    )
    assert s.GOOGLE_REDIRECT_URI == "https://mentor-ai-api-onzd.onrender.com/api/v1/calendar/callback"
    assert s.GOOGLE_GMAIL_REDIRECT_URI == "https://mentor-ai-api-onzd.onrender.com/api/v1/gmail/callback"
    assert s.FRONTEND_URL == "https://frontend-ten-delta-a5irgspmf7.vercel.app"


def test_oauth_redirect_uri_auto_heal_render_typo():
    """Auto-heals missing -onzd slug typo from Render environment variables."""
    s = Settings(
        ENVIRONMENT="production",
        GOOGLE_REDIRECT_URI="https://mentor-ai-api.onrender.com/api/v1/calendar/callback",
        GOOGLE_GMAIL_REDIRECT_URI="https://mentor-ai-api.onrender.com/api/v1/gmail/callback",
    )
    assert s.GOOGLE_REDIRECT_URI == "https://mentor-ai-api-onzd.onrender.com/api/v1/calendar/callback"
    assert s.GOOGLE_GMAIL_REDIRECT_URI == "https://mentor-ai-api-onzd.onrender.com/api/v1/gmail/callback"


def test_calendar_authorization_url_matches_registered_redirect():
    """Verifies that GoogleCalendarAdapter uses the exact configured redirect URI."""
    with patch.object(settings, "GOOGLE_CLIENT_ID", "test-client-id"), \
         patch.object(settings, "GOOGLE_CLIENT_SECRET", "test-client-secret"), \
         patch.object(settings, "GOOGLE_REDIRECT_URI", "https://mentor-ai-api-onzd.onrender.com/api/v1/calendar/callback"):
        adapter = GoogleCalendarAdapter()
        auth_url = adapter.get_authorization_url(state="test-state-123")
        parsed = urllib.parse.urlparse(auth_url)
        params = urllib.parse.parse_qs(parsed.query)

        assert params["redirect_uri"] == ["https://mentor-ai-api-onzd.onrender.com/api/v1/calendar/callback"]
        assert params["client_id"] == ["test-client-id"]
        assert params["response_type"] == ["code"]
        assert params["access_type"] == ["offline"]


def test_gmail_authorization_url_matches_registered_redirect():
    """Verifies that GoogleGmailAdapter uses the exact configured redirect URI."""
    with patch.object(settings, "GOOGLE_CLIENT_ID", "test-client-id"), \
         patch.object(settings, "GOOGLE_CLIENT_SECRET", "test-client-secret"), \
         patch.object(settings, "GOOGLE_GMAIL_REDIRECT_URI", "https://mentor-ai-api-onzd.onrender.com/api/v1/gmail/callback"):
        adapter = GoogleGmailAdapter()
        auth_url = adapter.get_authorization_url(state="test-state-gmail")
        parsed = urllib.parse.urlparse(auth_url)
        params = urllib.parse.parse_qs(parsed.query)

        assert params["redirect_uri"] == ["https://mentor-ai-api-onzd.onrender.com/api/v1/gmail/callback"]
        assert params["client_id"] == ["test-client-id"]
        assert params["response_type"] == ["code"]
        assert params["access_type"] == ["offline"]


@pytest.mark.asyncio
async def test_calendar_callback_denial_browser_redirect():
    """When user cancels on Google consent screen, browser navigation redirects to frontend with error."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get(
            "/api/v1/calendar/callback?error=access_denied&error_description=User+declined+permissions",
            headers={"Accept": "text/html"},
            follow_redirects=False,
        )
        assert res.status_code == 303
        loc = res.headers["location"]
        assert "/calendar" in loc
        assert "error=access_denied" in loc


@pytest.mark.asyncio
async def test_calendar_callback_denial_api_error():
    """When caller is an API client, OAuth denial raises HTTP 400 error envelope."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get(
            "/api/v1/calendar/callback?error=access_denied&error_description=User+declined+permissions",
            headers={"Accept": "application/json"},
        )
        assert res.status_code == 400
        data = res.json()
        assert data["error_code"] == "OAUTH_ACCESS_DENIED"


@pytest.mark.asyncio
async def test_gmail_callback_denial_browser_redirect():
    """When user cancels on Google consent screen for Gmail, browser navigation redirects to frontend."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get(
            "/api/v1/gmail/callback?error=access_denied&error_description=User+declined+permissions",
            headers={"Accept": "text/html"},
            follow_redirects=False,
        )
        assert res.status_code == 303
        loc = res.headers["location"]
        assert "/gmail" in loc
        assert "error=access_denied" in loc


@pytest.mark.asyncio
async def test_gmail_callback_denial_api_error():
    """When caller is an API client, Gmail denial raises HTTP 400 error envelope."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get(
            "/api/v1/gmail/callback?error=access_denied&error_description=User+declined+permissions",
            headers={"Accept": "application/json"},
        )
        assert res.status_code == 400
        data = res.json()
        assert data["error_code"] == "OAUTH_ACCESS_DENIED"


@pytest.mark.asyncio
async def test_calendar_callback_success_browser_redirect(test_db: AsyncSession):
    """Successful calendar authorization redirects browser to frontend calendar page with connected status."""
    user_id = uuid.uuid4()
    profile = Profile(id=user_id, email="alice.cal@test.edu", timezone="UTC")
    test_db.add(profile)
    await test_db.commit()

    mock_cal = MockCalendarAdapter()
    state = generate_oauth_state(user_id=user_id, provider=mock_cal.provider_name)

    with patch.object(CalendarService, "get_provider", return_value=mock_cal):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get(
                f"/api/v1/calendar/callback?code=mock-code-123&state={state}",
                headers={"Accept": "text/html"},
                follow_redirects=False,
            )
            assert res.status_code == 303
            loc = res.headers["location"]
            assert "/calendar" in loc
            assert "connected=true" in loc


@pytest.mark.asyncio
async def test_gmail_callback_success_browser_redirect(test_db: AsyncSession):
    """Successful Gmail authorization redirects browser to frontend gmail page with connected status."""
    user_id = uuid.uuid4()
    profile = Profile(id=user_id, email="bob.gmail@test.edu", timezone="UTC")
    test_db.add(profile)
    await test_db.commit()

    state = generate_oauth_state(user_id=user_id, provider="google_gmail")

    with patch.object(GmailService, "get_provider", return_value=MockGmailAdapter()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get(
                f"/api/v1/gmail/callback?code=mock-code-gmail-123&state={state}",
                headers={"Accept": "text/html"},
                follow_redirects=False,
            )
            assert res.status_code == 303
            loc = res.headers["location"]
            assert "/gmail" in loc
            assert "connected=true" in loc


@pytest.mark.asyncio
async def test_callback_tampered_state_rejected():
    """Tampered OAuth state token is rejected with HTTP 400."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get(
            "/api/v1/calendar/callback?code=mock-code-123&state=tampered-fake-state",
            headers={"Accept": "application/json"},
        )
        assert res.status_code == 400
        data = res.json()
        assert data["error_code"] == "INVALID_OAUTH_STATE"
