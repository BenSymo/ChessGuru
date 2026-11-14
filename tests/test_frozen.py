"""The packaged app (ChessGuru.exe): paths, Stockfish, dbt and the double-click start."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from chessguru import cli, frozen
from chessguru.config import Settings


@pytest.fixture
def packaged(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Pretend to be the packaged app, with its files in tmp_path/bundle."""
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    return bundle


def test_not_frozen_by_default() -> None:
    assert not frozen.is_frozen()
    assert frozen.bundled_stockfish() is None
    assert Settings().data_dir == Path("./data")
    assert frozen.dbt_command()[1] == "-c"


def test_packaged_app_keeps_data_in_the_user_folder(packaged: Path, tmp_path: Path) -> None:
    assert frozen.app_data_dir() == tmp_path / "appdata" / "ChessGuru"
    assert Settings().data_dir == tmp_path / "appdata" / "ChessGuru"


def test_data_folder_without_localappdata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    assert frozen.app_data_dir() == Path.home() / ".chessguru"


def test_packaged_app_reads_settings_from_its_data_folder(packaged: Path, tmp_path: Path) -> None:
    folder = tmp_path / "appdata" / "ChessGuru"
    folder.mkdir(parents=True)
    (folder / ".env").write_text("CHESSGURU_USERNAME=Someone\n")
    from chessguru import config

    assert Settings(_env_file=config._env_files()).username == "someone"


def test_packaged_app_uses_its_own_stockfish(
    packaged: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("shutil.which", lambda name: "/elsewhere/stockfish")
    assert Settings().resolve_stockfish() == Path("/elsewhere/stockfish")  # not bundled yet

    (packaged / "stockfish").mkdir()
    binary = packaged / "stockfish" / "stockfish.exe"
    binary.write_text("")
    assert Settings().resolve_stockfish() == binary


def test_packaged_app_runs_dbt_through_itself(packaged: Path) -> None:
    assert frozen.dbt_command() == [sys.executable, frozen.DBT_COMMAND]


def test_main_with_no_arguments_opens_the_dashboard(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[list[str]] = []
    monkeypatch.setattr(sys, "argv", ["ChessGuru.exe"])
    monkeypatch.setattr(cli, "app", lambda: called.append(list(sys.argv)))
    frozen.main()
    assert called == [["ChessGuru.exe", "dashboard"]]


def test_main_passes_other_commands_through(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[list[str]] = []
    monkeypatch.setattr(sys, "argv", ["ChessGuru.exe", "doctor"])
    monkeypatch.setattr(cli, "app", lambda: called.append(list(sys.argv)))
    frozen.main()
    assert called == [["ChessGuru.exe", "doctor"]]


def test_main_runs_dbt(monkeypatch: pytest.MonkeyPatch) -> None:
    import dbt.cli.main

    called: list[list[str]] = []
    monkeypatch.setattr(sys, "argv", ["ChessGuru.exe", frozen.DBT_COMMAND, "build", "--quiet"])
    monkeypatch.setattr(dbt.cli.main, "cli", lambda: called.append(list(sys.argv)))
    frozen.main()
    assert called == [["dbt", "build", "--quiet"]]


def test_dashboard_command(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[list[str]] = []
    monkeypatch.setattr(cli, "_run_streamlit", seen.append)
    result = CliRunner().invoke(cli.app, ["dashboard", "--port", "8600"])
    assert result.exit_code == 0
    args = seen[0]
    assert args[:2] == ["streamlit", "run"]
    assert args[2].endswith("main.py")
    assert "8600" in args
    assert "--global.developmentMode" not in args


def test_dashboard_command_when_packaged(packaged: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[list[str]] = []
    monkeypatch.setattr(cli, "_run_streamlit", seen.append)
    result = CliRunner().invoke(cli.app, ["dashboard"])
    assert result.exit_code == 0
    assert "--global.developmentMode" in seen[0]
    assert "Close it to stop ChessGuru" in result.output
