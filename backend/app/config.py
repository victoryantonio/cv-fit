"""Application configuration. Environment only; no config files with secrets."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

CsvList = Annotated[list[str], NoDecode]


def _split_csv(value: Any) -> Any:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


class Settings(BaseSettings):
    """All runtime knobs. `.env` is read only as a convenience for local runs."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = "sqlite:///data/app.db"
    data_dir: Path = Path("data")
    prompts_dir: Path = Path("prompts")
    #: Stage B build output. Missing means "serve the API only": no error.
    ui_dist_dir: Path = Path("frontend/dist")

    llm_base_url: str = "http://127.0.0.1:8000/v1"
    llm_model: str = "deepseek-v4-flash"
    llm_max_concurrency: int = Field(default=2, ge=1, le=8)
    match_runs: int = Field(default=3, ge=1, le=5)

    blocked_fetch_hosts: CsvList = ["linkedin.com"]
    allowed_hosts: CsvList = ["127.0.0.1", "localhost"]
    allowed_origins: CsvList = ["http://localhost:5173", "http://127.0.0.1:5173"]
    # FR-24 custom redaction terms. They live in config for now because cvs may
    # not import the platform module; A7 moves them into the settings service.
    redaction_terms: CsvList = []
    parser_timeout_seconds: float = Field(default=30.0, gt=0)

    cover_note_min_words: int = Field(default=60, ge=1)
    cover_note_max_words: int = Field(default=150, ge=2)

    gmail_client_secret_path: Path | None = None
    gmail_mcp_command: str = "python -m app.mcp_gmail"
    token_budget_monthly: int = Field(default=0, ge=0)

    worker_enabled: bool = True
    worker_poll_seconds: float = Field(default=1.5, gt=0)
    task_stale_seconds: int = Field(default=900, gt=0)

    log_level: str = "INFO"
    upload_max_bytes: int = Field(default=5 * 1024 * 1024, ge=1024)

    @field_validator(
        "blocked_fetch_hosts",
        "allowed_hosts",
        "allowed_origins",
        "redaction_terms",
        mode="before",
    )
    @classmethod
    def _csv(cls, value: Any) -> Any:
        return _split_csv(value)

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    def ensure_dirs(self) -> None:
        """Create the directories the app writes to. Called once at startup."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "uploads").mkdir(parents=True, exist_ok=True)
        (self.data_dir / "backups").mkdir(parents=True, exist_ok=True)
