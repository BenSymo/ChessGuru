from pathlib import Path

import pytest

from chessguru.config import Settings
from chessguru.db import SCHEMA_VERSION, connect
from chessguru.governance.hashing import KEY_FILE, load_key, make_hasher


def test_hash_is_stable_case_insensitive_and_hides_the_name() -> None:
    hash_name = make_hasher(b"key-1")

    assert hash_name("Opponent") == hash_name(" opponent ")
    assert "opponent" not in hash_name("Opponent")
    assert len(hash_name("Opponent")) == 16


def test_different_keys_give_different_hashes() -> None:
    assert make_hasher(b"key-1")("opponent") != make_hasher(b"key-2")("opponent")


def test_key_from_settings(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, hash_key="from-env")

    assert load_key(settings) == b"from-env"
    assert not (tmp_path / KEY_FILE).exists()


def test_key_is_created_once_and_kept_private(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)

    first = load_key(settings)
    second = load_key(settings)

    assert first == second
    assert len(first) == 64
    assert (tmp_path / KEY_FILE).stat().st_mode & 0o077 == 0


def test_old_silver_tables_are_rebuilt(tmp_path: Path) -> None:
    db = tmp_path / "old.duckdb"
    import duckdb

    old = duckdb.connect(str(db))
    old.execute("CREATE TABLE silver_games (username VARCHAR)")
    old.execute("INSERT INTO silver_games VALUES ('x')")
    old.close()

    conn = connect(db)

    columns = [r[0] for r in conn.execute("DESCRIBE silver_games").fetchall()]
    assert "opponent_key" in columns
    assert conn.execute("SELECT count(*) FROM silver_games").fetchone() == (0,)
    assert conn.execute("SELECT version FROM schema_version").fetchone() == (SCHEMA_VERSION,)


@pytest.mark.parametrize("times", [1, 2])
def test_connect_is_safe_to_repeat(tmp_path: Path, times: int) -> None:
    for _ in range(times):
        connect(tmp_path / "db.duckdb").close()
    conn = connect(tmp_path / "db.duckdb")
    assert conn.execute("SELECT count(*) FROM schema_version").fetchone() == (1,)
