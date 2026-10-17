"""Application configuration managed via Pydantic Settings."""

from pydantic import Field, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Core application settings with environment variable overrides."""

    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env"),
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

    # OpenAI Intelligence Layer & Voice Copilot (Phase 9)
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = Field(default="gpt-4o-mini", description="OpenAI chat/agent model name")
    OPENAI_TTS_MODEL: str = Field(default="tts-1", description="OpenAI text-to-speech model")
    OPENAI_STT_MODEL: str = Field(default="whisper-1", description="OpenAI speech-to-text model")
    OPENAI_DEFAULT_VOICE: str = Field(default="nova", description="Default OpenAI TTS voice preset")

    # Calendar Integration & OAuth
    CALENDAR_PROVIDER: str = Field(default="google_calendar", description="google_calendar | mock")
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/v1/calendar/callback"
    CALENDAR_ENCRYPTION_KEY: str = ""
    CALENDAR_REQUEST_TIMEOUT_SECONDS: float = Field(
        default=10.0, description="Calendar provider HTTP timeout"
    )

    # Persistent Notification Engine
    NOTIFICATION_DISPATCH_SECRET: str = Field(
        default="",
        description="Secret token for triggering secured notification dispatch",
    )
    NOTIFICATION_DEFAULT_LEAD_TIME_MINUTES: int = Field(
        default=30, description="Default lead time in minutes before deadline"
    )
    NOTIFICATION_MAX_RETRY_ATTEMPTS: int = Field(
        default=3, description="Maximum retry attempts for failed notifications"
    )
    NOTIFICATION_LEASE_DURATION_SECONDS: int = Field(
        default=300, description="Worker claim lease duration in seconds"
    )
    NOTIFICATION_BASE_BACKOFF_SECONDS: int = Field(
        default=60, description="Base exponential backoff seconds on delivery failure"
    )

    # Gmail Integration & OAuth
    GMAIL_PROVIDER: str = Field(default="google_gmail", description="google_gmail | mock")
    GOOGLE_GMAIL_CLIENT_ID: str = ""
    GOOGLE_GMAIL_CLIENT_SECRET: str = ""
    GOOGLE_GMAIL_REDIRECT_URI: str = "http://localhost:8000/api/v1/gmail/callback"
    GMAIL_REQUEST_TIMEOUT_SECONDS: float = Field(
        default=10.0, description="Gmail provider HTTP timeout"
    )

    # External Application URLs
    FRONTEND_URL: str = Field(
        default="https://frontend-ten-delta-a5irgspmf7.vercel.app",
        description="Public frontend URL for OAuth redirects",
    )
    BACKEND_PUBLIC_URL: str = Field(
        default="https://mentor-ai-api-onzd.onrender.com",
        description="Canonical public backend URL",
    )
    RENDER_EXTERNAL_URL: str = ""

    # Optional External Delivery Channels (SMTP / Push)
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = ""
    VAPID_PUBLIC_KEY: str = ""
    VAPID_PRIVATE_KEY: str = ""

    @field_validator("FRONTEND_URL", mode="after")
    @classmethod
    def assemble_frontend_url(cls, v: str, info: ValidationInfo) -> str:
        """Ensure frontend URL is trimmed without trailing slashes and appropriate for environment."""
        env = str(info.data.get("ENVIRONMENT", "development")).lower()
        cleaned = v.strip().rstrip("/") if v else ""
        if env != "production" and (cleaned == "https://frontend-ten-delta-a5irgspmf7.vercel.app" or not cleaned):
            return "http://localhost:3000"
        return cleaned or "https://frontend-ten-delta-a5irgspmf7.vercel.app"

    @field_validator("GOOGLE_REDIRECT_URI", mode="after")
    @classmethod
    def assemble_google_redirect_uri(cls, v: str, info: ValidationInfo) -> str:
        """Ensure Google Calendar redirect URI is valid, HTTPS in production, and strips trailing slashes."""
        env = str(info.data.get("ENVIRONMENT", "development")).lower()
        render_ext = str(info.data.get("RENDER_EXTERNAL_URL", "")).strip().rstrip("/")
        backend_base = (
            render_ext
            or str(info.data.get("BACKEND_PUBLIC_URL", "https://mentor-ai-api-onzd.onrender.com")).strip().rstrip("/")
        )

        val = v.strip().rstrip("/") if v else ""

        # In production mode: prevent localhost leaks and auto-heal known typo missing -onzd
        if env == "production":
            if not val or "localhost" in val or "127.0.0.1" in val or "mentor-ai-api.onrender.com" in val:
                return f"{backend_base}/api/v1/calendar/callback"

        return val or f"{backend_base}/api/v1/calendar/callback"

    @field_validator("GOOGLE_GMAIL_REDIRECT_URI", mode="after")
    @classmethod
    def assemble_google_gmail_redirect_uri(cls, v: str, info: ValidationInfo) -> str:
        """Ensure Google Gmail redirect URI is valid, HTTPS in production, and strips trailing slashes."""
        env = str(info.data.get("ENVIRONMENT", "development")).lower()
        render_ext = str(info.data.get("RENDER_EXTERNAL_URL", "")).strip().rstrip("/")
        backend_base = (
            render_ext
            or str(info.data.get("BACKEND_PUBLIC_URL", "https://mentor-ai-api-onzd.onrender.com")).strip().rstrip("/")
        )

        val = v.strip().rstrip("/") if v else ""

        # In production mode: prevent localhost leaks and auto-heal known typo missing -onzd
        if env == "production":
            if not val or "localhost" in val or "127.0.0.1" in val or "mentor-ai-api.onrender.com" in val:
                return f"{backend_base}/api/v1/gmail/callback"

        return val or f"{backend_base}/api/v1/gmail/callback"

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

    @property
    def has_google_gmail_credentials(self) -> bool:
        """Check whether valid Google Gmail OAuth credentials have been configured."""
        cid = self.GOOGLE_GMAIL_CLIENT_ID or self.GOOGLE_CLIENT_ID
        csec = self.GOOGLE_GMAIL_CLIENT_SECRET or self.GOOGLE_CLIENT_SECRET
        return bool(cid and csec and "placeholder" not in cid.lower())

    @property
    def has_notification_dispatch_secret(self) -> bool:
        """Check whether a notification dispatch secret is configured."""
        return bool(self.NOTIFICATION_DISPATCH_SECRET)

    @property
    def has_email_credentials(self) -> bool:
        """Check whether SMTP email credentials are configured."""
        return bool(self.SMTP_HOST and self.SMTP_FROM_EMAIL)

    @property
    def has_push_credentials(self) -> bool:
        """Check whether browser push VAPID credentials are configured."""
        return bool(self.VAPID_PUBLIC_KEY and self.VAPID_PRIVATE_KEY)

    @property
    def has_openai_credentials(self) -> bool:
        """Check whether valid OpenAI API credentials have been configured."""
        return bool(
            self.OPENAI_API_KEY
            and self.OPENAI_API_KEY.strip()
            and "placeholder" not in self.OPENAI_API_KEY.lower()
        )


# Singleton settings instance
settings = Settings()
