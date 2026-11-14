"""Settings, read from environment variables or a local .env file.

Every setting uses the CHESSGURU_ prefix, e.g. CHESSGURU_MAX_GAMES=30.
Secrets live in .env (gitignored), never in code.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from chessguru import __version__


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CHESSGURU_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    username: str | None = None
    contact: str | None = None
    data_dir: Path = Path("./data")
    stockfish_path: Path | None = None
    engine_depth: int = Field(default=14, ge=1, le=40)
    max_games: int = Field(default=30, ge=1)
    hash_key: SecretStr | None = None
    dbt_project_dir: Path | None = None

    @field_validator("username", "contact", "stockfish_path", "hash_key", mode="before")
    @classmethod
    def _blank_is_none(cls, value: object) -> object:
        """Treat empty values from .env (e.g. `CHESSGURU_CONTACT=`) as unset."""
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("username")
    @classmethod
    def _normalise_username(cls, value: str | None) -> str | None:
        # chess.com usernames are case-insensitive; the API uses lower case.
        return value.strip().lower() if value else value

    @property
    def user_agent(self) -> str:
        """User-Agent for chess.com requests. Chess.com asks for contact details."""
        base = f"ChessGuru/{__version__}"
        return f"{base} (contact: {self.contact})" if self.contact else base

    @property
    def db_path(self) -> Path:
        return self.data_dir / "chessguru.duckdb"

    @property
    def bronze_dir(self) -> Path:
        return self.data_dir / "bronze"

    @property
    def dbt_target_dir(self) -> Path:
        """Where dbt puts compiled SQL and the docs site."""
        return self.data_dir / "dbt_target"

    def resolve_stockfish(self) -> Path | None:
        """Return the Stockfish binary to use, or None if it can't be found."""
        if self.stockfish_path:
            return self.stockfish_path if self.stockfish_path.exists() else None
        found = shutil.which("stockfish")
        return Path(found) if found else None
