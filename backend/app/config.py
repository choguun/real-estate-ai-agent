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
    jwt_secret_previous: str = ""  # cycle 6 T-604: rollover window
    jwt_algorithm: str = "HS256"
    jwt_alg: str = "HS256"
    var_dir: str = "var"
    jwt_ttl_seconds: int = 60 * 60 * 24

    supabase_storage_bucket: str = "uploads"
    public_base_url: str = "http://localhost:8000"
    supabase_storage_private: bool = False
    frontend_url: str = "http://localhost:3000"

    # Stripe (cycle 4 T-405)  -- set USE_MOCKS=false to enable
    stripe_api_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_growth: str = ""
    stripe_price_team: str = ""

    cors_origins: list[str] = ["*"]

    # ── Cycle 6 T-601 rate-limit policies ──
    # Override these via env to tighten or relax per environment.
    # Defaults: 5 login attempts / 15min per IP, 5 signups / hr per
    # IP (anti-enumeration), 20 invitations / hr per owner.
    rate_limit_login_per_15min: int = 5
    rate_limit_signup_per_hour: int = 5
    rate_limit_invite_per_hour: int = 20
    # ── Cycle 7 T-701: distributed rate-limit backend selection ──
    # Set to "redis" in multi-pod prod for cluster-wide limit state.
    # "memory" (default) is single-process; fine for dev / single-pod.
    rate_limit_backend: str = "memory"
    redis_url: str = "redis://localhost:6379/0"
    # ── Cycle 8 T-801: MFA TOTP encryption key ──
    # 32-byte URL-safe base64-encoded Fernet key. Generate with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # Empty default = dev mode (T-501's `validate_mfa_encryption_key`
    # accepts empty in dev; production requires a real key).
    mfa_encryption_key: str = ""

    # ── Cycle 5 T-501 fail-fast validators ──
    # Call `settings.validate_security()` after construction (or from
    # `create_app()`) to ensure non-dev deployments don't ship with
    # insecure defaults. See `app/security_validation.py`.

    def validate_security(self) -> None:
        """Run all security validators. Raises ValueError on failure.

        Named `validate_security` (not `validate`) because Pydantic's
        BaseModel already defines a classmethod `validate` with a
        different signature; overriding would break Pydantic.
        """
        # Imported here to avoid a circular import at module-load time.
        from app.security_validation import (
            validate_cors_origins,
            validate_jwt_secret,
            validate_jwt_secret_previous,
            validate_line_channel_secret,
            validate_mfa_encryption_key,
            validate_stripe_api_key,
        )

        validate_jwt_secret(self.jwt_secret, env=self.env)
        validate_jwt_secret_previous(self.jwt_secret_previous, env=self.env)
        validate_mfa_encryption_key(self.mfa_encryption_key, env=self.env)
        validate_cors_origins(self.cors_origins, env=self.env)
        validate_line_channel_secret(self.line_channel_secret, env=self.env)
        validate_stripe_api_key(self.stripe_api_key, use_mocks=self.use_mocks, env=self.env)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached Settings instance."""
    return Settings()
