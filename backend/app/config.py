"""Application configuration.

All runtime values come from environment variables (or `.env`).
Routers/services import `get_settings()` only — never read env directly.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings. Mock-first defaults — flip flags to enable real adapters."""

    # ── App ─────────────────────────────────────────────────────────────
    app_name: str = "Real Estate AI Agent"
    app_version: str = "0.1.0"
    env: str = "development"
    cors_origins: list[str] = ["http://localhost:3000"]

    # ── Adapter flags ───────────────────────────────────────────────────
    use_mocks: bool = True
    use_real_supabase: bool = False
    use_real_line: bool = False
    use_real_ai: bool = False

    # ── Secrets / real-adapter URLs (placeholders for local dev) ────────
    jwt_secret: str = "dev-jwt-secret-change-me"
    jwt_alg: str = "HS256"
    jwt_ttl_seconds: int = 3600

    line_channel_secret: str = "dev-line-channel-secret-change-me"
    line_channel_access_token: str = "dev-line-channel-access-token-change-me"
    line_default_agent_id: str | None = None

    anthropic_api_key: str = "dev-anthropic-key-change-me"
    anthropic_model: str = "claude-3-5-sonnet-latest"
    gemini_api_key: str = "dev-gemini-key-change-me"
    gemini_model: str = "gemini-2.0-flash-exp"

    supabase_url: str = "https://example.supabase.co"
    supabase_anon_key: str = "dev-supabase-anon-key"
    supabase_service_role_key: str = "dev-supabase-service-role-key"

    # ── Mock storage ────────────────────────────────────────────────────
    var_dir: str = "var"
    public_base_url: str = "http://localhost:8000"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    """Cached settings — call this everywhere."""
    return Settings()
