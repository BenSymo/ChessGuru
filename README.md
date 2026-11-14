# ChessGuru

Quickly see where you're going wrong at chess and what to fix first to reach the next level.

ChessGuru downloads your games from chess.com, scores every move with Stockfish, and ranks your
biggest weaknesses by how many games they cost you. Everything runs on your own machine.

> **Status:** early development. Milestones 1–2 are done: setup, and downloading + checking games. See [the plan](docs/PLAN.md).

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
any it can't use (variants like Chess960, custom start positions, broken data). Past months are
kept on disk, so later runs only download what's new.

Use `--games 100` to look at more games than the default 30.

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
