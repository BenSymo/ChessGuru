# ChessGuru

Quickly see where you're going wrong at chess and what to fix first to reach the next level.

ChessGuru downloads your games from chess.com, scores every move with Stockfish, and ranks your
biggest weaknesses by how many games they cost you. Everything runs on your own machine.

> **Status:** early development. Milestones 1–5 are done: downloading and checking games, splitting them into moves, Stockfish analysis, and the gold tables. See [the plan](docs/PLAN.md).

## What you need

- Python 3.12 or newer
- [uv](https://docs.astral.sh/uv/) to install and run the project
- [Stockfish](https://stockfishchess.org/download/) (the chess engine)
  - macOS: `brew install stockfish`
  - Ubuntu/Debian: `sudo apt install stockfish`
  - Windows: download it, then set `CHESSGURU_STOCKFISH_PATH` in `.env`

## Set up

```bash
git clone https://github.com/BenSymo/ChessGuru.git
cd ChessGuru
uv sync
cp .env.example .env   # then fill it in
uv run chessguru doctor
```

`doctor` checks your settings and that Stockfish can be found.

## Download your games

```bash
uv run chessguru fetch <your-username>
```

This downloads your most recent months of games into `data/bronze/`, checks them, and sets aside
any it can't use (variants like Chess960, custom start positions, broken data). Each game is
then split into one row per move, with clock times and time spent (the silver layer). Past months are
kept on disk, so later runs only download what's new.

Use `--games 100` to look at more games than the default 30.

## Analyse your games

```bash
uv run chessguru run <you>                # everything, newest 30 games
uv run chessguru run <you> --games 100    # analyse more games
uv run chessguru analyse <you> --depth 18 # just the Stockfish step, deeper
```

Stockfish scores every position. Each move is then labelled by how much it lowered
your chance of winning (Lichess's thresholds):

| Label | Drop in win chance |
|---|---|
| Inaccuracy `?!` | 5+ points |
| Mistake `?` | 10+ points |
| Blunder `??` | 15+ points |

Bad moves are also tagged with a reason where one can be spotted: `hanging_piece`,
`missed_fork`, `missed_pin`, `missed_skewer`, `missed_mate`, `allowed_mate`,
`missed_punish` (the opponent had just gone wrong) and `low_clock` (under 10% of your
time left). Each game is split into opening, middlegame and endgame.

Results are saved, so changing the number of games only analyses the extra ones.
Expect roughly 2–3 seconds per game on a 4-core laptop at depth 14. To change the
default, set `CHESSGURU_MAX_GAMES` and `CHESSGURU_ENGINE_DEPTH` in `.env`.

## Build the gold tables

```bash
uv run chessguru build      # just the dbt step
uv run chessguru run <you>  # fetch + check + parse + analyse + build
uv run chessguru docs       # dbt docs site with lineage
```

dbt turns the silver tables into a star schema in the `gold` schema of
`data/chessguru.duckdb`:

| Table | One row per |
|---|---|
| `fact_game` | game, from your side of the board |
| `fact_move` | move (both sides; `is_player_move` marks yours) |
| `dim_player` | rating change per time class (Type 2: history is kept) |
| `dim_opponent` | opponent, known only by a keyed hash of their username |
| `dim_opening`, `dim_time_control`, `dim_date` | opening, time control, day |
| `mart_*` | ready-made summaries for the dashboard |

Every build also runs the dbt tests: keys are unique, facts link to their
dimensions, every silver game reaches gold, and no real opponent names appear.

## Privacy

Opponents' usernames are hashed with HMAC-SHA256 before they reach the gold
tables. The key is `CHESSGURU_HASH_KEY`, or a random key created in
`data/.hash_key` on first run. Your `data/` folder and `.env` are never committed.

## Settings

All settings go in `.env`. See [`.env.example`](.env.example) for the full list.

| Setting | Default | What it does |
|---|---|---|
| `CHESSGURU_USERNAME` | none | Your chess.com username |
| `CHESSGURU_CONTACT` | none | Contact details for the User-Agent header, as chess.com asks |
| `CHESSGURU_MAX_GAMES` | `30` | How many recent games to analyse |
| `CHESSGURU_ENGINE_DEPTH` | `14` | Stockfish search depth |
| `CHESSGURU_DATA_DIR` | `./data` | Where games and the database are stored |

## Run with Docker

The image includes Stockfish.

```bash
docker build -t chessguru .
docker run --rm --env-file .env chessguru doctor
```

## Development

```bash
uv run ruff check .        # lint
uv run ruff format .       # format
uv run mypy src tests      # type check
uv run pytest              # tests with coverage
```

CI runs all of these, then builds the Docker image, on every push and pull request.
