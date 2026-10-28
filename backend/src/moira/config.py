"""Configuration from environment variables, read once and validated at startup.

Every variable is listed in blueprint Appendix A, in ``.env.example`` and in
``docs/reference/CONFIG.md``; CI checks the three agree (§13.9).
"""

import subprocess
from datetime import date, time
from functools import cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from moira import __version__
from moira.errors import ConfigError

BACKEND_DIR = Path(__file__).resolve().parents[2]

# Appendix A marks these "yes (prod)": optional in dev and test, required in prod.
PROD_REQUIRED = ("model_api_key",)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["dev", "test", "prod"] = "dev"
    public_base_url: str
    data_dir: Path = Path("/var/lib/moira")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    default_tz: str = "Asia/Kathmandu"

    telegram_bot_token: SecretStr
    telegram_bot_username: str
    owner_telegram_id: int

    model_api_key: SecretStr | None = None
    model_api_base: str = "https://api.meta.ai/v1"
    model_main: str = "muse-spark-1.3"
    model_contrib: str = "muse-spark-1.3-contributor"
    model_asr: str = "muse-voice-transcribe-1.0"
    structured_transport: Literal["responses", "chat"] = "responses"
    ai_enabled: bool = True

    embed_model: str = "minishlab/potion-retrieval-32M"
    embed_dim: int = 256
    embed_quantize: str = "int8"
    hf_home: Path | None = None
    hf_hub_offline: bool = False

    cap_global_daily_usd: float = 3.00
    cap_owner_daily_usd: float = 1.50
    cap_tester_daily_usd: float = 0.30
    cap_judge_daily_usd: float = 0.40
    cap_sandbox_daily_usd: float = 0.10
    cap_web_searches_daily: int = 150
    cap_video_daily: int = 10
    cap_total_usd: float = 120.0

    worker_concurrency: int = Field(default=3, ge=1)
    sandbox_ttl_hours: int = 24
    sandbox_max_active: int = 200
    sandbox_create_per_ip_hour: int = 5
    judge_access_until: date = date(2026, 11, 20)
    session_days: int = 90
    login_token_minutes: int = 10

    github_token: SecretStr | None = None
    digest_local_time: time = time(8, 0)
    nightly_local_time: time = time(3, 30)

    backup_age_recipient: str | None = None
    backup_rclone_remote: str | None = None
    backup_keep_daily: int = 14
    backup_keep_weekly: int = 8

    # Read by the DuckDNS timer and Caddy, not by the app; listed so the three-way check holds.
    duckdns_domain: str | None = None
    duckdns_token: SecretStr | None = None
    moira_host: str | None = None

    @property
    def model_cache_dir(self) -> Path:
        return self.hf_home or self.data_dir / "models"

    @property
    def fake_llm(self) -> bool:
        """FakeLLM in tests, and in dev when no API key is set (``make dev``)."""
        return self.app_env == "test" or self.model_api_key is None


def load_settings() -> Settings:
    """Build settings, or stop with the names of the missing or invalid variables."""
    try:
        settings = Settings()  # values come from the environment
    except ValidationError as exc:
        errors = exc.errors()
        missing = sorted({str(e["loc"][0]).upper() for e in errors if e["type"] == "missing"})
        invalid = sorted({str(e["loc"][0]).upper() for e in errors if e["type"] != "missing"})
        parts = []
        if missing:
            parts.append("missing required environment variable(s): " + ", ".join(missing))
        if invalid:
            parts.append("invalid environment variable(s): " + ", ".join(invalid))
        raise ConfigError("; ".join(parts)) from None
    if settings.app_env == "prod":
        absent = [name.upper() for name in PROD_REQUIRED if getattr(settings, name) is None]
        if absent:
            raise ConfigError("missing required environment variable(s): " + ", ".join(absent))
    return settings


@cache
def app_version() -> str:
    """The running version (§13.6): a deployed ``VERSION`` file, else ``git describe``."""
    version_file = BACKEND_DIR / "VERSION"
    if version_file.is_file():
        return version_file.read_text(encoding="utf-8").strip()
    try:
        out = subprocess.run(
            ["git", "describe", "--tags", "--always", "--dirty"],  # noqa: S607
            cwd=BACKEND_DIR,
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return __version__
    return out.stdout.strip() or __version__
