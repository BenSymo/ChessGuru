"""Bronze storage and downloading only the months that are needed."""

import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
import respx

from chessguru.api.client import BASE_URL, ArchiveMonth, ChessComClient
from chessguru.ingest.bronze import BronzeStore
from chessguru.ingest.fetch import count_games, fetch_recent_games
from tests.factories import archives_json, make_game, month_json

MONTH_URL = f"{BASE_URL}/player/testplayer/games"


@pytest.fixture
def store(tmp_path: Path) -> BronzeStore:
    return BronzeStore(tmp_path / "bronze")


@pytest.fixture
def client() -> ChessComClient:
    return ChessComClient("t", delay=0, sleep=lambda _: None)


def test_bronze_round_trip(store: BronzeStore) -> None:
    month = ArchiveMonth(2026, 10)
    raw = b'{"games": []}'

    path = store.write("TestPlayer", month, raw)

    assert path == store.root / "testplayer" / "2026-10.json"
    assert store.read("testplayer", month) == raw
    assert list(path.parent.glob("*.tmp")) == []


def test_bronze_lists_months_oldest_first(store: BronzeStore) -> None:
    for m in (ArchiveMonth(2026, 10), ArchiveMonth(2025, 1)):
        store.write("testplayer", m, b"{}")
    (store.root / "testplayer" / "notes.json").write_text("{}")

    assert store.months("testplayer") == [ArchiveMonth(2025, 1), ArchiveMonth(2026, 10)]
    assert store.months("nobody") == []


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (month_json(make_game(1), make_game(2)), 2),
        (b'{"games": []}', 0),
        (b"not json", 0),
        (b"[]", 0),
        (b'{"games": "oops"}', 0),
    ],
)
def test_count_games(raw: bytes, expected: int) -> None:
    assert count_games(raw) == expected


@respx.mock
def test_fetch_stops_once_it_has_enough_games(client: ChessComClient, store: BronzeStore) -> None:
    respx.get(f"{MONTH_URL}/archives").respond(
        json=archives_json("testplayer", "2026-09", "2026-10", "2026-11")
    )
    respx.get(f"{MONTH_URL}/2026/11").respond(content=month_json(make_game(1)))
    respx.get(f"{MONTH_URL}/2026/10").respond(content=month_json(make_game(2), make_game(3)))
    september = respx.get(f"{MONTH_URL}/2026/09").respond(content=month_json(make_game(4)))

    summary = fetch_recent_games(client, store, "testplayer", 3)

    assert summary.downloaded == [ArchiveMonth(2026, 11), ArchiveMonth(2026, 10)]
    assert summary.games_found == 3
    assert not september.called


@respx.mock
def test_fetch_reuses_complete_months_but_refreshes_others(
    client: ChessComClient, store: BronzeStore
) -> None:
    _write_at(store, ArchiveMonth(2026, 10), month_json(make_game(2)), datetime(2026, 11, 2))
    _write_at(store, ArchiveMonth(2026, 11), month_json(), datetime(2026, 11, 13))
    respx.get(f"{MONTH_URL}/archives").respond(
        json=archives_json("testplayer", "2026-10", "2026-11")
    )
    respx.get(f"{MONTH_URL}/2026/11").respond(content=month_json(make_game(1)))
    october = respx.get(f"{MONTH_URL}/2026/10")

    summary = fetch_recent_games(client, store, "testplayer", 30)

    assert summary.downloaded == [ArchiveMonth(2026, 11)]
    assert summary.cached == [ArchiveMonth(2026, 10)]
    assert not october.called
    assert count_games(store.read("testplayer", ArchiveMonth(2026, 11))) == 1


def _write_at(store: BronzeStore, month: ArchiveMonth, raw: bytes, when: datetime) -> None:
    """Store a month file as if it had been downloaded at `when` (UTC)."""
    path = store.write("testplayer", month, raw)
    stamp = when.replace(tzinfo=UTC).timestamp()
    os.utime(path, (stamp, stamp))


def test_month_is_complete_only_if_downloaded_after_it_ended(store: BronzeStore) -> None:
    october = ArchiveMonth(2026, 10)
    assert not store.is_complete("testplayer", october)  # not stored
    _write_at(store, october, b"{}", datetime(2026, 10, 20))
    assert not store.is_complete("testplayer", october)  # downloaded mid-month
    _write_at(store, october, b"{}", datetime(2026, 11, 1))
    assert store.is_complete("testplayer", october)
    assert ArchiveMonth(2026, 12).ends_at() == datetime(2027, 1, 1, tzinfo=UTC)


@respx.mock
def test_fetch_redownloads_a_month_first_fetched_while_it_was_going(
    client: ChessComClient, store: BronzeStore
) -> None:
    # October was downloaded on 20 October, so games from later that month are missing.
    _write_at(store, ArchiveMonth(2026, 10), month_json(make_game(2)), datetime(2026, 10, 20))
    respx.get(f"{MONTH_URL}/archives").respond(json=archives_json("testplayer", "2026-10"))
    respx.get(f"{MONTH_URL}/2026/10").respond(content=month_json(make_game(2), make_game(3)))

    summary = fetch_recent_games(client, store, "testplayer", 30)

    assert summary.downloaded == [ArchiveMonth(2026, 10)]
    assert count_games(store.read("testplayer", ArchiveMonth(2026, 10))) == 2
