"""Google Calendar API v3 provider implementation using HTTP client."""

import asyncio
from datetime import UTC, datetime, timedelta
from datetime import time as dtime
from typing import Any
from urllib.parse import urlencode

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.services.calendar.base import (
    CalendarAuthExpiredException,
    CalendarAuthRevokedException,
    CalendarProvider,
    CalendarProviderException,
    CalendarRateLimitException,
    CalendarTimeoutException,
)
from app.services.calendar.models import (
    CalendarEventCreate,
    NormalizedCalendarEvent,
    OAuthTokenData,
)

logger = get_logger("mentor_ai.calendar.google")

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
GOOGLE_CALENDAR_API_BASE = "https://www.googleapis.com/calendar/v3"

# Minimum required scopes for event reading, scheduling, and email identification
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]


class GoogleCalendarAdapter(CalendarProvider):
    """Production adapter for Google Calendar API v3."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    @property
    def provider_name(self) -> str:
        return "google_calendar"

    def get_authorization_url(self, state: str) -> str:
        """Construct the Google OAuth 2.0 authorization URL."""
        if not settings.has_google_calendar_credentials:
            raise CalendarProviderException(
                "Google Calendar credentials are not configured in environment.",
                status_code=503,
            )

        params = {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "redirect_uri": settings.GOOGLE_REDIRECT_URI,
            "response_type": "code",
            "scope": " ".join(GOOGLE_SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
        return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        return httpx.AsyncClient(timeout=settings.CALENDAR_REQUEST_TIMEOUT_SECONDS)

    async def _execute_with_retry(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Execute an HTTP request with bounded exponential backoff for rate limits.

        To guarantee reliability and prevent duplicate mutations, non-idempotent actions (POST)
        are NOT retried blindly on timeouts or transient server errors.
        """
        client = await self._get_client()
        is_idempotent = method.upper() in ("GET", "HEAD", "OPTIONS", "PUT", "DELETE")
        max_retries = 3 if is_idempotent else 1
        delay = 1.0

        for attempt in range(max_retries):
            try:
                response = await client.request(method, url, **kwargs)

                if response.status_code == 401:
                    # Token expired or invalid
                    raise CalendarAuthExpiredException()
                elif response.status_code in (429, 503):
                    if attempt == max_retries - 1:
                        raise CalendarRateLimitException()
                    await asyncio.sleep(delay)
                    delay *= 2.0
                    continue
                return response
            except httpx.TimeoutException as exc:
                if attempt == max_retries - 1:
                    raise CalendarTimeoutException() from exc
                await asyncio.sleep(delay)
                delay *= 1.5
            except (CalendarAuthExpiredException, CalendarRateLimitException):
                raise
            except Exception as exc:
                if attempt == max_retries - 1:
                    raise CalendarProviderException(f"Network error: {exc}") from exc
                await asyncio.sleep(delay)

        raise CalendarProviderException("Max retries exceeded.")

    async def exchange_code(self, code: str) -> OAuthTokenData:
        """Exchange authorization code for tokens and fetch account email."""
        data = {
            "code": code,
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uri": settings.GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
        }

        try:
            client = await self._get_client()
            res = await client.post(GOOGLE_TOKEN_URL, data=data)
        except httpx.TimeoutException as exc:
            raise CalendarTimeoutException() from exc
        except Exception as exc:
            raise CalendarProviderException(f"Failed to exchange code: {exc}") from exc

        if res.status_code != 200:
            error_body = (
                res.json()
                if res.headers.get("content-type", "").startswith("application/json")
                else {}
            )
            error_desc = error_body.get("error_description", res.text)
            raise CalendarProviderException(
                f"OAuth code exchange failed: {error_desc}", status_code=res.status_code
            )

        token_json = res.json()
        access_token = token_json["access_token"]
        refresh_token = token_json.get("refresh_token")
        expires_in = token_json.get("expires_in", 3600)
        expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
        scopes = token_json.get("scope", "").split()

        # Fetch account email for identification
        account_email: str | None = None
        try:
            userinfo_res = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if userinfo_res.status_code == 200:
                account_email = userinfo_res.json().get("email")
        except Exception as exc:
            logger.warning("Could not fetch Google userinfo email", error=str(exc))

        return OAuthTokenData(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type=token_json.get("token_type", "Bearer"),
            expires_in=expires_in,
            expires_at=expires_at,
            scopes=scopes,
            account_email=account_email,
        )

    async def refresh_token(self, refresh_token: str) -> OAuthTokenData:
        """Obtain a fresh access token using refresh_token."""
        data = {
            "refresh_token": refresh_token,
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "grant_type": "refresh_token",
        }

        try:
            client = await self._get_client()
            res = await client.post(GOOGLE_TOKEN_URL, data=data)
        except httpx.TimeoutException as exc:
            raise CalendarTimeoutException() from exc
        except Exception as exc:
            raise CalendarProviderException(f"Token refresh failed: {exc}") from exc

        if res.status_code == 400 or res.status_code == 401:
            body = (
                res.json()
                if res.headers.get("content-type", "").startswith("application/json")
                else {}
            )
            if body.get("error") in ("invalid_grant", "unauthorized_client"):
                raise CalendarAuthRevokedException()
            raise CalendarAuthExpiredException()

        if res.status_code != 200:
            raise CalendarProviderException(
                f"Failed to refresh Google token: {res.text}", status_code=res.status_code
            )

        token_json = res.json()
        expires_in = token_json.get("expires_in", 3600)
        return OAuthTokenData(
            access_token=token_json["access_token"],
            refresh_token=token_json.get("refresh_token") or refresh_token,
            token_type=token_json.get("token_type", "Bearer"),
            expires_in=expires_in,
            expires_at=datetime.now(UTC) + timedelta(seconds=expires_in),
            scopes=token_json.get("scope", "").split(),
        )

    async def revoke_token(self, token: str) -> bool:
        """Revoke active token with Google."""
        try:
            client = await self._get_client()
            res = await client.post(GOOGLE_REVOKE_URL, data={"token": token})
            return res.status_code == 200
        except Exception as exc:
            logger.warning("Failed to revoke token at provider", error=str(exc))
            return False

    async def list_events(
        self, access_token: str, start_time: datetime, end_time: datetime
    ) -> list[NormalizedCalendarEvent]:
        """Fetch and normalize Google Calendar events with pagination support."""
        events: list[NormalizedCalendarEvent] = []
        page_token: str | None = None
        base_url = f"{GOOGLE_CALENDAR_API_BASE}/calendars/primary/events"

        while True:
            params: dict[str, Any] = {
                "timeMin": start_time.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "timeMax": end_time.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "singleEvents": "true",
                "orderBy": "startTime",
                "maxResults": 250,
            }
            if page_token:
                params["pageToken"] = page_token

            headers = {"Authorization": f"Bearer {access_token}"}
            res = await self._execute_with_retry("GET", base_url, params=params, headers=headers)

            if res.status_code != 200:
                raise CalendarProviderException(
                    f"Google Calendar list failed ({res.status_code}): {res.text}",
                    status_code=res.status_code,
                )

            data = res.json()
            for item in data.get("items", []):
                normalized = self._parse_google_event(item)
                if normalized:
                    events.append(normalized)

            page_token = data.get("nextPageToken")
            if not page_token:
                break

        return events

    async def get_event(
        self, access_token: str, external_id: str
    ) -> NormalizedCalendarEvent | None:
        """Fetch individual event by ID for truthful post-condition verification."""
        url = f"{GOOGLE_CALENDAR_API_BASE}/calendars/primary/events/{external_id}"
        headers = {"Authorization": f"Bearer {access_token}"}

        res = await self._execute_with_retry("GET", url, headers=headers)
        if res.status_code == 404:
            return None
        if res.status_code != 200:
            raise CalendarProviderException(
                f"Google Calendar get_event failed: {res.text}", status_code=res.status_code
            )

        return self._parse_google_event(res.json())

    async def create_event(
        self, access_token: str, event_data: CalendarEventCreate
    ) -> NormalizedCalendarEvent:
        """Create event on Google Calendar and immediately verify outcome with follow-up read."""
        url = f"{GOOGLE_CALENDAR_API_BASE}/calendars/primary/events"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        body: dict[str, Any] = {
            "summary": event_data.title,
            "description": event_data.description,
            "location": event_data.location,
        }

        if event_data.is_all_day:
            body["start"] = {"date": event_data.start_time.strftime("%Y-%m-%d")}
            body["end"] = {"date": event_data.end_time.strftime("%Y-%m-%d")}
        else:
            body["start"] = {
                "dateTime": event_data.start_time.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "timeZone": "UTC",
            }
            body["end"] = {
                "dateTime": event_data.end_time.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "timeZone": "UTC",
            }

        res = await self._execute_with_retry("POST", url, json=body, headers=headers)
        if res.status_code not in (200, 201):
            raise CalendarProviderException(
                f"Google Calendar create failed ({res.status_code}): {res.text}",
                status_code=res.status_code,
            )

        created_data = res.json()
        external_id = created_data.get("id")

        # Truthful follow-up read verification
        verified_event = await self.get_event(access_token, external_id)
        if not verified_event:
            raise CalendarProviderException(
                f"Post-condition verification failed: created event {external_id} could not be read back from Google Calendar.",
                status_code=502,
            )

        return verified_event

    async def delete_event(self, access_token: str, external_id: str) -> bool:
        """Delete an event on Google Calendar."""
        url = f"{GOOGLE_CALENDAR_API_BASE}/calendars/primary/events/{external_id}"
        headers = {"Authorization": f"Bearer {access_token}"}

        res = await self._execute_with_retry("DELETE", url, headers=headers)
        return res.status_code in (200, 204)

    def _parse_google_event(self, item: dict[str, Any]) -> NormalizedCalendarEvent | None:
        """Parse raw Google Calendar API JSON item into normalized entity."""
        if item.get("status") == "cancelled":
            return None

        event_id = item.get("id")
        if not event_id or not isinstance(event_id, str):
            return None

        title = item.get("summary", "(No Title)")
        description = item.get("description")
        location = item.get("location")
        html_link = item.get("htmlLink")
        etag = item.get("etag")

        start_raw = item.get("start", {})
        end_raw = item.get("end", {})

        is_all_day = "date" in start_raw
        if is_all_day:
            start_date_str = start_raw.get("date")
            end_date_str = end_raw.get("date")
            if not start_date_str or not end_date_str:
                return None
            start_dt = datetime.combine(
                datetime.strptime(start_date_str, "%Y-%m-%d").date(), dtime.min, tzinfo=UTC
            )
            # Google all-day end dates are exclusive; convert to midnight UTC
            end_dt = datetime.combine(
                datetime.strptime(end_date_str, "%Y-%m-%d").date(), dtime.min, tzinfo=UTC
            )
        else:
            start_iso = start_raw.get("dateTime")
            end_iso = end_raw.get("dateTime")
            if not start_iso or not end_iso:
                return None
            start_dt = datetime.fromisoformat(start_iso).astimezone(UTC)
            end_dt = datetime.fromisoformat(end_iso).astimezone(UTC)

        return NormalizedCalendarEvent(
            external_id=event_id,
            title=title,
            description=description,
            start_time=start_dt,
            end_time=end_dt,
            is_all_day=is_all_day,
            location=location,
            status=item.get("status", "confirmed"),
            html_link=html_link,
            etag=etag,
        )
