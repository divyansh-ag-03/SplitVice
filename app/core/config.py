from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/splitvice"

    # ── JWT ───────────────────────────────────────────────────────────────────
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── App ───────────────────────────────────────────────────────────────────
    DEBUG: bool = False
    APP_VERSION: str = "0.1.0"
    # "development" | "production" — controls secure cookies, log format, etc.
    ENV: str = "development"

    # ── Security ──────────────────────────────────────────────────────────────
    # Comma-separated list of allowed hosts (used in production).
    # Example: "splitvice.example.com,www.splitvice.example.com"
    ALLOWED_HOSTS: str = "*"

    # ── Sentry ────────────────────────────────────────────────────────────────
    # Leave empty to disable Sentry (default for local development).
    SENTRY_DSN: str = ""

    @field_validator("JWT_SECRET")
    @classmethod
    def jwt_secret_min_length(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters long")
        return v

    @property
    def is_production(self) -> bool:
        return self.ENV.lower() == "production"

    @property
    def cookie_secure(self) -> bool:
        """Secure flag on cookies — True only in production (requires HTTPS)."""
        return self.is_production


# Module-level singleton — import this everywhere
settings = Settings()
