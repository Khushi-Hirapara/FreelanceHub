"""Application settings. Secrets must come from the environment."""

from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

INSECURE_SECRET_KEYS = frozenset(
    {
        "freelancehub-dev-secret-change-in-production",
        "change-me-to-a-long-random-string",
        "your-long-random-secret",
        "secret",
        "changeme",
    }
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql://postgres:password@localhost:5432/freelancehub"
    # No insecure default — must be provided via SECRET_KEY in the environment / .env
    secret_key: str = ""
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    cors_origins: str = "http://localhost:5500,http://127.0.0.1:5500,http://localhost:3000"
    # development | production
    app_env: str = "development"
    # Fraction of agreed_amount kept by the platform. Not a payment processor.
    platform_fee_rate: float = 0.10
    # mock = demo self-confirm payments; disabled = block payment mutations (use before real PSP)
    payments_mode: str = "mock"
    bcrypt_rounds: int = 12

    # Object storage. local = private filesystem keys; s3 = private bucket via boto3.
    storage_provider: str = "local"
    storage_local_root: str = "storage"
    attachment_max_bytes: int = 10 * 1024 * 1024
    s3_bucket: str = ""
    s3_region: str = "us-east-1"
    s3_endpoint_url: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""

    # Gemini — server-side only. Never expose the key to the frontend.
    # Completely separate from SECRET_KEY (JWT).
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.6-flash"
    gemini_timeout_seconds: float = 30.0

    # Simple in-process rate limits (per IP). Use Redis/gateway limits in production scale-out.
    rate_limit_enabled: bool = True
    rate_limit_auth_per_minute: int = 20
    rate_limit_ai_per_minute: int = 10
    rate_limit_upload_per_minute: int = 30

    @property
    def cors_origin_list(self) -> list[str]:
        origins = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        if self.is_production:
            return [o for o in origins if o.lower() != "null"]
        return origins

    @property
    def is_production(self) -> bool:
        return self.app_env.strip().lower() in {"production", "prod"}

    @field_validator("payments_mode")
    @classmethod
    def normalize_payments_mode(cls, value: str) -> str:
        mode = (value or "mock").strip().lower()
        if mode not in {"mock", "disabled"}:
            raise ValueError("PAYMENTS_MODE must be 'mock' or 'disabled'")
        return mode

    @field_validator("bcrypt_rounds")
    @classmethod
    def bcrypt_rounds_range(cls, value: int) -> int:
        if value < 10 or value > 16:
            raise ValueError("BCRYPT_ROUNDS must be between 10 and 16")
        return value

    @model_validator(mode="after")
    def validate_secrets(self) -> "Settings":
        key = (self.secret_key or "").strip()
        if not key:
            raise ValueError(
                "SECRET_KEY must be set in the environment (see backend/.env.example). "
                "Do not rely on a code default."
            )
        if key in INSECURE_SECRET_KEYS or len(key) < 32:
            if self.is_production:
                raise ValueError(
                    "Production SECRET_KEY must be a unique random string of at least 32 characters "
                    "and must not use a development placeholder."
                )
        if self.is_production and self.payments_mode == "mock":
            # Soft guard: still allow boot, but operators should disable until a real PSP exists.
            pass
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()
