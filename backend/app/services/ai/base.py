"""Abstract base class interface for AI model adapters."""

from abc import ABC, abstractmethod

from app.schemas.planner import ParserType
from app.services.ai.models import LLMParseResult, UserPlanContext


class BaseLLMAdapter(ABC):
    """Provider-agnostic interface for natural-language plan extraction."""

    @property
    @abstractmethod
    def name(self) -> ParserType:
        """The identifier name of this parser implementation."""
        pass

    @abstractmethod
    async def parse_instruction(self, prompt: str, context: UserPlanContext) -> LLMParseResult:
        """Parse untrusted user text into a structured DraftPlan.

        Args:
            prompt: Untrusted user natural language instruction.
            context: Verified user profile, working hours, and existing commitments.

        Returns:
            LLMParseResult containing the validated DraftPlan and parser metadata.

        Raises:
            AIProviderError: When the upstream model fails, times out, or violates constraints.
        """
        pass

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if this adapter has valid credentials and is operational."""
        pass


class AIProviderError(Exception):
    """Base exception for AI provider communication or validation failures."""

    def __init__(self, message: str, is_recoverable: bool = True, status_code: int = 502) -> None:
        super().__init__(message)
        self.message = message
        self.is_recoverable = is_recoverable
        self.status_code = status_code


class AIProviderTimeoutError(AIProviderError):
    """Exception raised when an AI provider call exceeds timeout thresholds."""

    def __init__(self, message: str = "AI provider request timed out") -> None:
        super().__init__(message, is_recoverable=True, status_code=504)


class AIProviderRateLimitError(AIProviderError):
    """Exception raised when an AI provider returns 429 Too Many Requests."""

    def __init__(self, message: str = "AI provider rate limit reached (HTTP 429)") -> None:
        super().__init__(message, is_recoverable=True, status_code=429)
