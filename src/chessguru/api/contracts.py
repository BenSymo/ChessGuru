"""The data contract: what we expect each game from chess.com to look like.

If chess.com changes its format, games fail this contract and are quarantined
instead of quietly producing wrong numbers further down the pipeline.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

STANDARD_START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


class _Contract(BaseModel):
    # Extra fields are fine (chess.com adds them over time); missing ones are not.
    model_config = ConfigDict(extra="ignore", frozen=True)


class Side(_Contract):
    username: str = Field(min_length=1)
    rating: int = Field(ge=0)
    result: str = Field(min_length=1)


class Game(_Contract):
    url: str = Field(pattern=r"^https://www\.chess\.com/game/")
    uuid: str = Field(min_length=1)
    pgn: str = Field(min_length=1)
    time_control: str = Field(min_length=1)
    time_class: Literal["bullet", "blitz", "rapid", "daily"]
    end_time: datetime
    rated: bool
    rules: str
    initial_setup: str = STANDARD_START
    white: Side
    black: Side
    eco: str | None = None

    def colour_of(self, username: str) -> Literal["white", "black"] | None:
        name = username.lower()
        if self.white.username.lower() == name:
            return "white"
        if self.black.username.lower() == name:
            return "black"
        return None
