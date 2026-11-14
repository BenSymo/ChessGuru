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

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 1
    assert "NOT FOUND" in result.stdout


def test_doctor_passes_with_stockfish(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    binary = tmp_path / "stockfish"
    binary.write_text("")
    monkeypatch.setenv("CHESSGURU_STOCKFISH_PATH", str(binary))

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert str(binary) in result.stdout
