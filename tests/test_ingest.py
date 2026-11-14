from datetime import date
from pathlib import Path

import pytest
import respx

from chessguru.api.client import BASE_URL, ArchiveMonth, ChessComClient
from chessguru.ingest.bronze import BronzeStore
from chessguru.ingest.fetch import count_games, fetch_recent_games
from tests.factories import archives_json, make_game, month_json

TODAY = date(2026, 11, 14)
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
    assert store.has("testplayer", month)
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

    summary = fetch_recent_games(client, store, "testplayer", 3, TODAY)

    assert summary.downloaded == [ArchiveMonth(2026, 11), ArchiveMonth(2026, 10)]
    assert summary.games_found == 3
    assert not september.called


@respx.mock
def test_fetch_reuses_past_months_but_refreshes_current(
    client: ChessComClient, store: BronzeStore
) -> None:
    store.write("testplayer", ArchiveMonth(2026, 10), month_json(make_game(2)))
    store.write("testplayer", ArchiveMonth(2026, 11), month_json())
    respx.get(f"{MONTH_URL}/archives").respond(
        json=archives_json("testplayer", "2026-10", "2026-11")
    )
    respx.get(f"{MONTH_URL}/2026/11").respond(content=month_json(make_game(1)))
    october = respx.get(f"{MONTH_URL}/2026/10")

    summary = fetch_recent_games(client, store, "testplayer", 30, TODAY)

    assert summary.downloaded == [ArchiveMonth(2026, 11)]
    assert summary.cached == [ArchiveMonth(2026, 10)]
    assert not october.called
    assert count_games(store.read("testplayer", ArchiveMonth(2026, 11))) == 1
