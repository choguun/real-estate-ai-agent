"""Application configuration loaded from environment / .env."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration.

    Attributes:
        app_name: Display name of the service (used in FastAPI metadata + /).
        app_version: Semver (used in FastAPI metadata + /).
        env: Deployment environment label (dev, staging, prod, ...).
        use_mocks: Master switch — when True, mocks win over per-adapter real flags.
        use_real_supabase: Use real Supabase DB + Storage when use_mocks=False.
        use_real_line: Use real LINE Messaging API when use_mocks=False.
        use_real_ai: Use real Anthropic + Gemini when use_mocks=False.
        supabase_url: Project URL for real Supabase.
        supabase_anon_key: Anon key for real Supabase.
        supabase_service_role_key: Service-role key (bypasses RLS, admin-only).
        line_channel_secret: LINE channel secret used to verify webhook signatures.
        line_channel_access_token: LINE channel access token used to send replies.
        line_default_agent_id: P1-W3 — if set, the LINE webhook attributes
            all inbound events to this agent. Empty = fallback.
        line_default_team_id: P1-W3 — if set, the LINE webhook attributes
            all inbound events to this team_id directly. Empty = use agent.
        anthropic_api_key: API key for Anthropic Claude.
        anthropic_model: Claude model name.
        gemini_api_key: API key for Google Gemini.
        gemini_model: Gemini model name.
        ai_provider: "anthropic" (default) or "gemini".
        jwt_secret: Symmetric secret used to sign FastAPI-issued JWTs.
        jwt_algorithm: JWT signing algorithm.
        jwt_ttl_seconds: JWT lifetime in seconds.
        supabase_storage_bucket: Storage bucket name (default "uploads").
        supabase_storage_private: If True, generate signed URLs (private bucket).
        frontend_url: Base URL of the frontend (for invite links).
        cors_origins: CORS allowed origins.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Real Estate AI Agent"
    app_version: str = "0.1.0"
    env: str = "dev"

    use_mocks: bool = True
    use_real_supabase: bool = False
    use_real_line: bool = False
    use_real_ai: bool = False

    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""

    line_channel_secret: str = "dev-line-channel-secret-change-me"
    line_channel_access_token: str = ""
    line_default_agent_id: str = ""
    line_default_team_id: str = ""

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-5-sonnet-latest"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    ai_provider: str = "anthropic"

    jwt_secret: str = "dev-jwt-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_alg: str = "HS256"
    var_dir: str = "var"
    jwt_ttl_seconds: int = 60 * 60 * 24

    supabase_storage_bucket: str = "uploads"
    public_base_url: str = "http://localhost:8000"
    supabase_storage_private: bool = False
    frontend_url: str = "http://localhost:3000"

    cors_origins: list[str] = ["*"]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached Settings instance."""
    return Settings()
