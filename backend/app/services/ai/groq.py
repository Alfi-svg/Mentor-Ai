"""Groq API model adapter using OpenAI-compatible chat completions."""

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


class GroqAdapter(BaseLLMAdapter):
    """Adapter for Groq Llama 3.3 70B via OpenAI-compatible REST API."""

    def __init__(self) -> None:
        self.api_key = settings.GROQ_API_KEY
        self.model = settings.GROQ_MODEL
        self.timeout = settings.AI_REQUEST_TIMEOUT_SECONDS
        self.max_retries = settings.AI_MAX_RETRIES
        self.base_url = "https://api.groq.com/openai/v1"

    @property
    def name(self) -> ParserType:
        return "groq"

    async def is_available(self) -> bool:
        """Check if Groq credentials are configured."""
        return bool(self.api_key and len(self.api_key.strip()) > 5)

    async def parse_instruction(self, prompt: str, context: UserPlanContext) -> LLMParseResult:
        """Query Groq API with prompt and context, returning a validated DraftPlan."""
        if not await self.is_available():
            raise AIProviderError(
                "GROQ_API_KEY is not configured or is invalid.", is_recoverable=True
            )

        sanitized_input = sanitize_user_input(prompt)
        system_prompt = build_system_prompt()

        context_block = (
            f"CONTEXT:\n"
            f"- Today's Date: {context.current_date.isoformat()}\n"
            f"- Timezone: {context.timezone}\n"
            f"- Configured Working Hours: {context.work_start_time.isoformat()} to {context.work_end_time.isoformat()}\n"
            f"- Minimum Meeting Buffer: {context.buffer_minutes} minutes\n"
            f"- Existing Events Today: {[e.model_dump() for e in context.existing_events]}\n"
            f"- Existing Pending Tasks: {[t.model_dump() for t in context.existing_tasks]}\n"
        )

        user_content = (
            f"{context_block}\n\n<user_instruction>\n{sanitized_input}\n</user_instruction>"
        )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }

        url = f"{self.base_url}/chat/completions"
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(url, headers=headers, json=payload)

                if response.status_code == 429:
                    raise AIProviderRateLimitError()

                if response.status_code != 200:
                    raise AIProviderError(
                        f"Groq API returned HTTP {response.status_code}: {response.text[:300]}",
                        status_code=response.status_code,
                    )

                data: dict[str, Any] = response.json()
                choices = data.get("choices", [])
                if not choices:
                    raise AIProviderError("Groq API returned 0 choices in response.")

                content = choices[0].get("message", {}).get("content", "")
                if not content:
                    raise AIProviderError("Groq API choice message content is empty.")

                draft_plan = repair_and_validate_json(content)

                return LLMParseResult(
                    draft_plan=draft_plan,
                    parser_used="groq",
                    raw_response=content,
                    metadata={"model": self.model},
                )

            except httpx.TimeoutException as exc:
                last_error = AIProviderTimeoutError(f"Groq request timed out after {self.timeout}s")
                logger.warning("groq_timeout", attempt=attempt, error=str(exc))
            except (AIProviderRateLimitError, AIProviderError) as exc:
                last_error = exc
                if exc.status_code == 429 or attempt >= self.max_retries:
                    raise
            except Exception as exc:
                last_error = AIProviderError(f"Unexpected error communicating with Groq: {exc}")
                logger.error("groq_call_failed", attempt=attempt, error=str(exc))

            if attempt < self.max_retries:
                await asyncio.sleep(0.5 * (2**attempt))

        if last_error:
            raise last_error
        raise AIProviderError("Groq provider failed after max retries.")
