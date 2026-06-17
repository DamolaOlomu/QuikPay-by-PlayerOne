"""
app/core/config.py
Centralised, validated settings loaded from environment / .env file.
"""
from functools import lru_cache
from typing import Literal
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ────────────────────────────────────────────────────────
    APP_NAME: str = "PlayerOnePay"
    APP_ENV: Literal["development", "staging", "production"] = "development"
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # ── API ────────────────────────────────────────────────────────────────
    API_V1_PREFIX: str = "/api/v1"
    ALLOWED_ORIGINS: str = "http://localhost:3000"

    # ── Database ───────────────────────────────────────────────────────────
    DATABASE_URL: str = "sqlite+aiosqlite:///./playeronepay_dev.db"
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20
    DATABASE_POOL_TIMEOUT: int = 30

    # ── Auth ───────────────────────────────────────────────────────────────
    JWT_SECRET_KEY: str = "CHANGE_ME_in_production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    BCRYPT_ROUNDS: int = 12

    # ── Security ───────────────────────────────────────────────────────────
    ENCRYPTION_KEY: str = "CHANGE_ME_32_char_key_here______"

    # ── Redis ──────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    RATE_LIMIT_PER_MINUTE: int = 60
    RATE_LIMIT_BURST: int = 10

    # ── Observability ──────────────────────────────────────────────────────
    SENTRY_DSN: str = ""

    # ── Webhooks ───────────────────────────────────────────────────────────
    WEBHOOK_SECRET: str = "CHANGE_ME_webhook_secret"
    WEBHOOK_MAX_RETRIES: int = 3
    WEBHOOK_TIMEOUT_SECONDS: int = 10

    # ── Payment Processor ──────────────────────────────────────────────────
    PAYMENT_PROCESSOR_API_KEY: str = ""
    PAYMENT_PROCESSOR_BASE_URL: str = "https://api.paymentprocessor.example.com"

    # Glyde payment processor
    GLYDE_ENABLED: bool = False
    GLYDE_SECRET_KEY: str = ""
    GLYDE_ENV: Literal["sandbox", "live"] = "sandbox"
    GLYDE_BASE_URL: str = "https://sandbox.useglyde.co/v1"
    GLYDE_WEBHOOK_SIGNING_KEY: str = ""

    @field_validator("DATABASE_URL")
    @classmethod
    def validate_db_url(cls, v: str) -> str:
        if not any(v.startswith(p) for p in ("sqlite", "postgresql", "mysql")):
            raise ValueError("DATABASE_URL must use sqlite, postgresql, or mysql scheme")
        return v

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def is_testing(self) -> bool:
        return self.APP_ENV == "development" and "test" in self.DATABASE_URL

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
