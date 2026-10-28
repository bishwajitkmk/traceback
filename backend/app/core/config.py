from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Process configuration, read from TRACEBACK_* environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="TRACEBACK_",
        env_file=(".env", "../.env"),
        extra="ignore",
    )

    env: Literal["development", "test", "production"] = "development"
    database_url: str = "postgresql+psycopg://traceback:traceback@localhost:5432/traceback"
    secret_key: str = Field(default="dev-insecure-secret", min_length=16)
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5180"]
    session_ttl_hours: int = Field(default=168, gt=0)
    max_event_bytes: int = Field(default=256 * 1024, gt=0)
    replay_allow_private_networks: bool = False
    replay_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    replay_max_response_bytes: int = Field(default=256 * 1024, gt=0)
    replay_max_concurrency: int = Field(default=8, gt=0)
    # Cookie scope. Set to the parent domain (e.g. ".example.com") when the app and
    # API are on sibling subdomains, so the frontend can read the CSRF cookie.
    cookie_domain: str | None = None
    # Number of reverse proxies in front of the API (Render: 1). Used to read the
    # client IP from X-Forwarded-For for rate limiting; 0 trusts no header.
    trusted_proxy_hops: int = Field(default=0, ge=0)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("database_url")
    @classmethod
    def _use_psycopg_driver(cls, value: str) -> str:
        # Hosts (Neon, Render) hand out bare postgres:// URLs, which SQLAlchemy maps to
        # psycopg2; only psycopg 3 is installed.
        for scheme in ("postgresql://", "postgres://"):
            if value.startswith(scheme):
                return "postgresql+psycopg://" + value[len(scheme) :]
        return value

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    @property
    def cookie_secure(self) -> bool:
        return self.is_production


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if settings.is_production:
        if settings.secret_key == "dev-insecure-secret":  # noqa: S105
            raise RuntimeError("TRACEBACK_SECRET_KEY must be set in production")
        if settings.replay_allow_private_networks:
            raise RuntimeError("Private-network replay cannot be enabled in production")
    return settings
