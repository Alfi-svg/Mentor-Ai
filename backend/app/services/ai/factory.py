"""AI Provider Factory with resilient, truthful fallback orchestration."""

import structlog

from app.core.config import settings
from app.services.ai.base import AIProviderError, BaseLLMAdapter
from app.services.ai.gemini import GeminiFlashAdapter
from app.services.ai.groq import GroqAdapter
from app.services.ai.models import LLMParseResult, UserPlanContext
from app.services.ai.offline import DeterministicOfflineAdapter

logger = structlog.get_logger(__name__)


def get_ai_adapter(provider_name: str | None = None) -> BaseLLMAdapter:
    """Instantiate the requested or configured AI adapter."""
    provider = (provider_name or settings.AI_PROVIDER).lower().strip()

    if provider == "gemini":
        return GeminiFlashAdapter()
    if provider == "groq":
        return GroqAdapter()
    return DeterministicOfflineAdapter()


async def parse_instruction_resilient(
    prompt: str, context: UserPlanContext, requested_provider: str | None = None
) -> LLMParseResult:
    """Execute plan extraction with automatic, truthfully disclosed fallback.

    If the primary provider (Gemini or Groq) fails or is unconfigured, and
    settings.AI_ALLOW_OFFLINE_FALLBACK is True, this runs the DeterministicOfflineAdapter
    and stamps fallback_applied=True with parser_used='deterministic_offline'.
    """
    primary_adapter = get_ai_adapter(requested_provider)

    # If offline was explicitly requested, execute directly
    if primary_adapter.name == "deterministic_offline":
        return await primary_adapter.parse_instruction(prompt, context)

    # Check primary provider availability
    is_available = await primary_adapter.is_available()
    if not is_available:
        if settings.AI_ALLOW_OFFLINE_FALLBACK:
            logger.info(
                "ai_provider_unavailable_fallback_engaged",
                primary=primary_adapter.name,
                reason="Credentials missing or empty",
            )
            offline_adapter = DeterministicOfflineAdapter()
            result = await offline_adapter.parse_instruction(prompt, context)
            result.fallback_applied = True
            result.metadata["primary_provider"] = primary_adapter.name
            result.metadata["fallback_reason"] = "Credentials missing"
            return result
        raise AIProviderError(
            f"Provider '{primary_adapter.name}' credentials are not configured and offline fallback is disabled.",
            status_code=503,
        )

    # Attempt primary provider call
    try:
        return await primary_adapter.parse_instruction(prompt, context)
    except Exception as exc:
        if settings.AI_ALLOW_OFFLINE_FALLBACK:
            logger.warning(
                "primary_ai_failed_engaging_fallback",
                primary=primary_adapter.name,
                error=str(exc),
            )
            offline_adapter = DeterministicOfflineAdapter()
            result = await offline_adapter.parse_instruction(prompt, context)
            result.fallback_applied = True
            result.metadata["primary_provider"] = primary_adapter.name
            result.metadata["fallback_reason"] = str(exc)
            return result
        raise
