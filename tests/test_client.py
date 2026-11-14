"""The chess.com API client: politeness, retries and errors (with a fake API)."""

import httpx
import pytest
import respx

from chessguru.api.client import (
    BASE_URL,
    ArchiveMonth,
    ChessComClient,
    ChessComError,
    PlayerNotFoundError,
)
from tests.factories import archives_json, make_game, month_json

ARCHIVES = f"{BASE_URL}/player/testplayer/games/archives"


@pytest.fixture
def sleeps() -> list[float]:
    return []


@pytest.fixture
def client(sleeps: list[float]) -> ChessComClient:
    return ChessComClient("ChessGuru/test", delay=0, backoff=1, sleep=sleeps.append)


@respx.mock
def test_archives_are_sorted_oldest_first(client: ChessComClient) -> None:
    respx.get(ARCHIVES).respond(json=archives_json("testplayer", "2026-10", "2025-03"))

    assert client.get_archives("TestPlayer") == [ArchiveMonth(2025, 3), ArchiveMonth(2026, 10)]


@respx.mock
def test_sends_user_agent(client: ChessComClient) -> None:
    route = respx.get(ARCHIVES).respond(json={"archives": []})

    client.get_archives("testplayer")

    assert route.calls.last.request.headers["User-Agent"] == "ChessGuru/test"


@respx.mock
def test_month_is_returned_as_raw_bytes(client: ChessComClient) -> None:
    raw = month_json(make_game())
    respx.get(f"{BASE_URL}/player/testplayer/games/2026/10").respond(content=raw)

    assert client.get_month_raw("testplayer", ArchiveMonth(2026, 10)) == raw


@respx.mock
def test_unknown_player(client: ChessComClient) -> None:
    respx.get(ARCHIVES).respond(404, json={"code": 0, "message": "not found"})

    with pytest.raises(PlayerNotFoundError, match="testplayer"):
        client.get_archives("testplayer")


@respx.mock
def test_retries_after_rate_limit(client: ChessComClient, sleeps: list[float]) -> None:
    respx.get(ARCHIVES).mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "7"}),
            httpx.Response(503),
            httpx.Response(200, json={"archives": []}),
        ]
    )

    assert client.get_archives("testplayer") == []
    assert sleeps == [7.0, 2.0]  # Retry-After first, then backoff for attempt 2


@respx.mock
def test_gives_up_after_max_retries(sleeps: list[float]) -> None:
    client = ChessComClient("t", delay=0, max_retries=2, sleep=sleeps.append)
    respx.get(ARCHIVES).respond(500)

    with pytest.raises(ChessComError, match="HTTP 500"):
        client.get_archives("testplayer")
    assert len(sleeps) == 2


@respx.mock
def test_network_errors_are_retried_then_reported(sleeps: list[float]) -> None:
    client = ChessComClient("t", delay=0, max_retries=1, sleep=sleeps.append)
    respx.get(ARCHIVES).mock(side_effect=httpx.ConnectError("boom"))

    with pytest.raises(ChessComError, match="Could not reach"):
        client.get_archives("testplayer")
    assert sleeps == [1.0]


@respx.mock
def test_waits_between_requests(sleeps: list[float]) -> None:
    client = ChessComClient("t", delay=60, sleep=sleeps.append)
    respx.get(ARCHIVES).respond(json={"archives": []})

    client.get_archives("testplayer")
    client.get_archives("testplayer")

    assert len(sleeps) == 1
    assert 59 < sleeps[0] <= 60


def test_client_closes_as_context_manager() -> None:
    with ChessComClient("t") as client:
        pass
    assert client._http.is_closed


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (f"{BASE_URL}/player/x/games/2026/01", ArchiveMonth(2026, 1)),
        (f"{BASE_URL}/player/x/games/1999/12", ArchiveMonth(1999, 12)),
    ],
)
def test_archive_month_from_url(url: str, expected: ArchiveMonth) -> None:
    assert ArchiveMonth.from_url(url) == expected
    assert expected.key == f"{expected.year:04d}-{expected.month:02d}"


def test_archive_month_rejects_odd_url() -> None:
    with pytest.raises(ChessComError):
        ArchiveMonth.from_url("https://example.com/whatever")
