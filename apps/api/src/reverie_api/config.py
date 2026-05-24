"""Application configuration.

Settings are read from environment variables (prefix ``REVERIE_``) with sane
defaults for local development. The same `Settings` object is used by tests,
which override values via constructor kwargs rather than env mutation.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="REVERIE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Storage
    db_path: Path = Field(
        default=Path("data/reverie.db"),
        description="Path to the SQLite database file. Parent dirs are auto-created.",
    )

    # Server
    host: str = Field(default="127.0.0.1")
    port: int = Field(default=8000)

    # Security
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000"],
        description="Allowed origins for browser clients.",
    )

    # Operational
    env: str = Field(default="development", description="dev | staging | production")

    # WebSocket
    ws_subscriber_buffer: int = Field(
        default=10_000,
        description="Per-subscriber outbound buffer size before dropping (back-pressure).",
        ge=100,
    )

    @property
    def is_dev(self) -> bool:
        return self.env.lower() in {"dev", "development", "local"}


def load_settings() -> Settings:
    """Build a fresh `Settings` from the current environment.

    Tests should call this once per app instance and pass an override-equipped
    instance via dependency injection rather than mutating env vars.
    """

    return Settings()
