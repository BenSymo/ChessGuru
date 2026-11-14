"""Settings and finding Stockfish."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from chessguru import __version__
from chessguru.config import Settings


def test_defaults() -> None:
    settings = Settings()

    assert settings.username is None
    assert settings.max_games == 30
    assert settings.engine_depth == 14
    assert settings.db_path == Path("data/chessguru.duckdb")
    assert settings.bronze_dir == Path("data/bronze")


def test_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHESSGURU_USERNAME", "  MagnusFan ")
    monkeypatch.setenv("CHESSGURU_MAX_GAMES", "100")

    settings = Settings()

    assert settings.username == "magnusfan"
    assert settings.max_games == 100


def test_reads_dotenv_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".env").write_text("CHESSGURU_USERNAME=fromfile\nCHESSGURU_CONTACT=\n")
    monkeypatch.chdir(tmp_path)

    settings = Settings()

    assert settings.username == "fromfile"
    assert settings.contact is None


@pytest.mark.parametrize(
    ("contact", "expected"),
    [
        (None, f"ChessGuru/{__version__}"),
        ("me@example.com", f"ChessGuru/{__version__} (contact: me@example.com)"),
    ],
)
def test_user_agent(contact: str | None, expected: str) -> None:
    assert Settings(contact=contact).user_agent == expected


@pytest.mark.parametrize("bad", [0, -5])
def test_max_games_must_be_positive(bad: int) -> None:
    with pytest.raises(ValidationError):
        Settings(max_games=bad)


def test_hash_key_is_hidden_when_printed() -> None:
    settings = Settings(hash_key="super-secret")

    assert "super-secret" not in repr(settings)
    assert settings.hash_key is not None
    assert settings.hash_key.get_secret_value() == "super-secret"


def test_resolve_stockfish_uses_configured_path(tmp_path: Path) -> None:
    binary = tmp_path / "stockfish"
    binary.write_text("")

    assert Settings(stockfish_path=binary).resolve_stockfish() == binary
    assert Settings(stockfish_path=tmp_path / "missing").resolve_stockfish() is None


def test_resolve_stockfish_searches_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", lambda name: "/usr/games/stockfish")

    assert Settings().resolve_stockfish() == Path("/usr/games/stockfish")


def test_resolve_stockfish_checks_common_folders(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = tmp_path / "stockfish"
    binary.write_text("")
    monkeypatch.setattr("shutil.which", lambda name: None)
    monkeypatch.setattr("chessguru.config.STOCKFISH_LOCATIONS", (tmp_path / "nope", binary))

    assert Settings().resolve_stockfish() == binary
