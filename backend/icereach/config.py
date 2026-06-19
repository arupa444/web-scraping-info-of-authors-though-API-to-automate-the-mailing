"""Application settings (pydantic-settings, env-overridable)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Storage
    database_url: str = "sqlite:///./icereach.db"

    # Security
    secret_key: str = "dev-insecure-change-me"
    session_cookie: str = "ice_session"
    csrf_cookie: str = "ice_csrf"
    session_max_age: int = 60 * 60 * 24 * 14  # 14 days

    # Public base URL used to build tracking + unsubscribe links
    base_url: str = "http://127.0.0.1:8000"

    # CORS origin for the SPA (Vite dev server by default)
    frontend_origin: str = "http://127.0.0.1:5173"

    # AI
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3-flash-preview"

    # Rate limiting (requests per IP per minute for API/public surfaces; 0 = disabled)
    rate_limit_per_minute: int = 600

    # Optional shared secret for inbound ESP webhooks (?secret=...); empty = no check
    webhook_secret: str = ""

    # Bounce mailbox (DSN poller) — optional in dev
    bounce_imap_host: str = ""
    bounce_imap_user: str = ""
    bounce_imap_password: str = ""


settings = Settings()
