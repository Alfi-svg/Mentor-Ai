"""Application configuration managed via Pydantic Settings."""

from pydantic import Field, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Core application settings with environment variable overrides."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # Project Information
    PROJECT_NAME: str = "Mentor AI API"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = Field(
        default="development", description="development | staging | production"
    )
    LOG_LEVEL: str = Field(default="INFO", description="DEBUG | INFO | WARNING | ERROR")

    # Networking
    HOST: str = "0.0.0.0"  # noqa: S104
    PORT: int = 8000

    # Security & CORS
    SECRET_KEY: str = Field(
        default="mentor-ai-dev-secret-key-change-in-production-min32chars",
        description="JWT signature verification or application secret",
    )
    ALLOWED_ORIGINS: list[str] | str = Field(
        default=["http://localhost:3000", "http://127.0.0.1:3000"],
        description="Origins permitted to make cross-origin requests",
    )

    # Supabase (PostgreSQL & Auth)
    SUPABASE_URL: str = ""
    SUPABASE_ANON_KEY: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    SUPABASE_JWT_SECRET: str = ""
    DATABASE_URL: str = ""
    TEST_DATABASE_URL: str = "sqlite+aiosqlite:///./test_mentor_ai.db"

    # AI Model Provider
    AI_PROVIDER: str = Field(default="offline", description="offline | gemini | groq")
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = Field(default="gemini-2.0-flash", description="Gemini model name")
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = Field(default="llama-3.3-70b-versatile", description="Groq model name")
    AI_REQUEST_TIMEOUT_SECONDS: float = Field(default=12.0, description="AI provider HTTP timeout")
    AI_MAX_RETRIES: int = Field(default=2, description="Max retry attempts for AI provider")
    AI_ALLOW_OFFLINE_FALLBACK: bool = Field(
        default=True, description="Whether to fall back to deterministic parser on API error"
    )

    # Calendar Integration & OAuth
    CALENDAR_PROVIDER: str = Field(default="google_calendar", description="google_calendar | mock")
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/v1/calendar/callback"
    CALENDAR_ENCRYPTION_KEY: str = ""
    CALENDAR_REQUEST_TIMEOUT_SECONDS: float = Field(
        default=10.0, description="Calendar provider HTTP timeout"
    )

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: str | list[str]) -> list[str]:
        """Convert comma-separated origin string into list of trimmed strings."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        if isinstance(v, list):
            return [str(origin).strip() for origin in v if str(origin).strip()]
        return ["http://localhost:3000", "http://127.0.0.1:3000"]

    @field_validator("ALLOWED_ORIGINS")
    @classmethod
    def validate_safe_origins(cls, origins: list[str], info: ValidationInfo) -> list[str]:
        """Ensure wildcards are not used when running in production."""
        # Note: In Pydantic v2, info.data gives access to other validated fields
        env = info.data.get("ENVIRONMENT", "development")
        if env == "production" and "*" in origins:
            raise ValueError("Wildcard '*' origin is strictly forbidden in production mode.")
        return origins

    @property
    def is_production(self) -> bool:
        """Helper to check if current environment is production."""
        return self.ENVIRONMENT.lower() == "production"

    @property
    def has_supabase_credentials(self) -> bool:
        """Check whether valid Supabase credentials have been configured."""
        return bool(
            self.SUPABASE_URL and self.SUPABASE_ANON_KEY and "placeholder" not in self.SUPABASE_URL
        )

    @property
    def has_database_url(self) -> bool:
        """Check whether a real database URL has been configured."""
        return bool(self.DATABASE_URL and "placeholder" not in self.DATABASE_URL)

    @property
    def has_google_calendar_credentials(self) -> bool:
        """Check whether valid Google Calendar OAuth credentials have been configured."""
        return bool(
            self.GOOGLE_CLIENT_ID
            and self.GOOGLE_CLIENT_SECRET
            and "placeholder" not in self.GOOGLE_CLIENT_ID.lower()
        )


# Singleton settings instance
settings = Settings()
