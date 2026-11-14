"""The command-line tool."""

import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from chessguru import __version__
from chessguru.cli import app

runner = CliRunner()


def test_version() -> None:
    result = runner.invoke(app, ["version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == __version__


def test_doctor_fails_without_stockfish(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", lambda name: None)
    monkeypatch.setattr("chessguru.config.STOCKFISH_LOCATIONS", ())

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 1
    assert "NOT FOUND" in result.stdout


def test_doctor_passes_with_stockfish() -> None:
    stockfish = shutil.which("stockfish") or "/usr/games/stockfish"
    if not Path(stockfish).exists():
        pytest.skip("Stockfish is not installed")

    result = runner.invoke(app, ["doctor"], env={"CHESSGURU_STOCKFISH_PATH": stockfish})

    assert result.exit_code == 0
    assert f"{stockfish} (working)" in result.stdout


def test_doctor_fails_when_stockfish_wont_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = tmp_path / "stockfish"
    binary.write_text("")  # not a program
    monkeypatch.setenv("CHESSGURU_STOCKFISH_PATH", str(binary))

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 1
    assert "WON'T START" in result.stdout
