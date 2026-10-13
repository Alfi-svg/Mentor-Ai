"""Google Gemini API model adapter using HTTP client."""

import asyncio
from typing import Any

import httpx
import structlog

from app.core.config import settings
from app.schemas.planner import ParserType
from app.services.ai.base import (
    AIProviderError,
    AIProviderRateLimitError,
    AIProviderTimeoutError,
    BaseLLMAdapter,
)
from app.services.ai.models import LLMParseResult, UserPlanContext
from app.services.ai.sanitizer import (
    build_system_prompt,
    repair_and_validate_json,
    sanitize_user_input,
)

logger = structlog.get_logger(__name__)


class GeminiFlashAdapter(BaseLLMAdapter):
    """Adapter for Google Gemini 1.5/2.5 Flash via direct HTTP REST API."""

    def __init__(self) -> None:
        self.api_key = settings.GEMINI_API_KEY
        self.model = settings.GEMINI_MODEL
        self.timeout = settings.AI_REQUEST_TIMEOUT_SECONDS
        self.max_retries = settings.AI_MAX_RETRIES
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"

    @property
    def name(self) -> ParserType:
        return "gemini"

    async def is_available(self) -> bool:
        """Check if Gemini credentials are configured."""
        return bool(self.api_key and len(self.api_key.strip()) > 5)

    async def parse_instruction(self, prompt: str, context: UserPlanContext) -> LLMParseResult:
        """Query Gemini API with prompt and context, returning a validated DraftPlan."""
        if not await self.is_available():
            raise AIProviderError(
                "GEMINI_API_KEY is not configured or is invalid.", is_recoverable=True
            )

        sanitized_input = sanitize_user_input(prompt)
        system_prompt = build_system_prompt()

        # Build context metadata
        context_block = (
            f"CONTEXT:\n"
            f"- Today's Date: {context.current_date.isoformat()}\n"
            f"- Timezone: {context.timezone}\n"
            f"- Configured Working Hours: {context.work_start_time.isoformat()} to {context.work_end_time.isoformat()}\n"
            f"- Minimum Meeting Buffer: {context.buffer_minutes} minutes\n"
            f"- Existing Events Today: {[e.model_dump() for e in context.existing_events]}\n"
            f"- Existing Pending Tasks: {[t.model_dump() for t in context.existing_tasks]}\n"
        )

        full_prompt = (
            f"{system_prompt}\n\n"
            f"{context_block}\n\n"
            f"<user_instruction>\n{sanitized_input}\n</user_instruction>"
        )

        url = f"{self.base_url}/models/{self.model}:generateContent?key={self.api_key}"
        payload = {
            "contents": [{"parts": [{"text": full_prompt}]}],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json",
            },
        }

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(url, json=payload)

                if response.status_code == 429:
                    raise AIProviderRateLimitError()

                if response.status_code != 200:
                    raise AIProviderError(
                        f"Gemini API returned HTTP {response.status_code}: {response.text[:300]}",
                        status_code=response.status_code,
                    )

                data: dict[str, Any] = response.json()
                candidates = data.get("candidates", [])
                if not candidates:
                    raise AIProviderError("Gemini API returned 0 candidates in response.")

                parts = candidates[0].get("content", {}).get("parts", [])
                if not parts or "text" not in parts[0]:
                    raise AIProviderError("Gemini API candidate response missing text part.")

                raw_text = parts[0]["text"]
                draft_plan = repair_and_validate_json(raw_text)

                return LLMParseResult(
                    draft_plan=draft_plan,
                    parser_used="gemini",
                    raw_response=raw_text,
                    metadata={"model": self.model},
                )

            except httpx.TimeoutException as exc:
                last_error = AIProviderTimeoutError(
                    f"Gemini request timed out after {self.timeout}s"
                )
                logger.warning("gemini_timeout", attempt=attempt, error=str(exc))
            except (AIProviderRateLimitError, AIProviderError) as exc:
                last_error = exc
                if exc.status_code == 429 or attempt >= self.max_retries:
                    raise
            except Exception as exc:
                last_error = AIProviderError(f"Unexpected error communicating with Gemini: {exc}")
                logger.error("gemini_call_failed", attempt=attempt, error=str(exc))

            if attempt < self.max_retries:
                await asyncio.sleep(0.5 * (2**attempt))

        if last_error:
            raise last_error
        raise AIProviderError("Gemini provider failed after max retries.")
