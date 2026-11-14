# ChessGuru

Quickly see where you're going wrong at chess and what to fix first to reach the next level.

ChessGuru downloads your games from chess.com, scores every move with Stockfish, and ranks your
biggest weaknesses by how many games they cost you. Everything runs on your own machine.

> **Status:** early development. Milestones 1–8 are done: downloading and checking games, Stockfish analysis, the gold tables, the dashboard, ranked tips, and a Windows app. See [the plan](docs/PLAN.md).

## Windows: download and run

No Python or Stockfish install needed. Everything is inside the app.

1. Download **ChessGuru-Setup.exe** from the [Releases page](https://github.com/BenSymo/ChessGuru/releases)
   (or, before the first release, from the latest successful **Windows app** run under the
   repository's **Actions** tab, in its **Artifacts** section).
2. Run it. Windows may say *"Windows protected your PC"* because the app isn't signed:
   click **More info**, then **Run anyway**.
3. Open **ChessGuru** from the Start menu or desktop. A window opens to show it's running and
   the dashboard opens in your browser. Close that window to stop ChessGuru.

Your games and settings are kept in `%LOCALAPPDATA%\ChessGuru`. To change a setting, put a
`.env` file there (see `.env.example`). The bundled Stockfish needs a CPU from about 2013 or newer
(AVX2). The app can also be used from a terminal, e.g. `ChessGuru.exe doctor`.

There is also **ChessGuru-portable.zip**: unzip it anywhere and run `ChessGuru.exe`, no install.

## Run from source

### What you need

- Python 3.12 or newer
- [uv](https://docs.astral.sh/uv/) to install and run the project
- [Stockfish](https://stockfishchess.org/download/) (the chess engine)
  - macOS: `brew install stockfish`
  - Ubuntu/Debian: `sudo apt install stockfish`
  - Windows: download it, then set `CHESSGURU_STOCKFISH_PATH` in `.env`

### Set up

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

## Quick start

```bash
uv run chessguru dashboard
```

This opens the dashboard in your browser. The first time, enter your chess.com username
and how many games to analyse, then press **Get my games**. After that:

- **Games to include** (sidebar) sets how many of your newest games the pages cover.
  If some aren't analysed yet, press **Analyse these games**.
- **Get new games from chess.com** downloads and analyses anything new.
- Filter by time control, colour, and rated games.

| Page | What it shows |
|---|---|
| Overview | Your top 3 things to fix, then score, accuracy, where and why your bad moves happen, rating |
| Tips | Every tip, ranked by what it cost you, with example positions from your games |
| Openings | Results per opening family as White and Black |
| Mistakes | Accuracy per phase, reasons for bad moves, your costliest moves with links |
| Time | Time per move, bad moves by clock left, losses on time |
| Endgames | Converting winning positions, endgame accuracy, how games finish |
| Game viewer | Step through any game on a board, with Stockfish's verdict and a win-chance chart |
| Data health | Pipeline runs, games set aside, row counts |

Everything can also be run from the command line, below.

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

## Tips

```bash
uv run chessguru tips <you>              # what to fix first, in the terminal
uv run chessguru tips <you> --games 100
```

Each tip rule checks one pattern: hanging pieces, missed tactics, missed or allowed mates,
not punishing mistakes, blunders when short of time, a weak game phase, letting winning
positions slip, openings that aren't working, losing on time, results after a loss, and a
gap between White and Black.

Tips are ranked by **cost**: roughly how many games' worth of points the problem cost you.
For bad moves, that is the drop in your chance of winning, added up per game and capped at
one game each. Each tip also says how many games it is based on, and whether it is a
**clear pattern** (3+ games out of 15+) or an **early sign**. Strengths are listed too.

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
docker run --rm --env-file .env -v "$PWD/data:/app/data" chessguru run <you>
docker run --rm --env-file .env -v "$PWD/data:/app/data" -p 8501:8501 chessguru dashboard
```

## Development

```bash
uv run ruff check .        # lint
uv run ruff format .       # format
uv run mypy src tests      # type check
uv run pytest              # tests with coverage
```

CI runs all of these, then builds the Docker image, on every push and pull request.

## Building the Windows app

The **Windows app** GitHub workflow builds it on every change: it bundles Python, the libraries,
the dbt project and Stockfish 17.1 with PyInstaller (`packaging/chessguru.spec`), checks the
packaged app works (doctor, a gold build, the dashboard starting), then wraps it in an installer
with Inno Setup (`packaging/installer.iss`). Pushing a tag like `v0.1.0` publishes a release.

Stockfish is free software under the GPL v3; its licence is shipped in the app's
`_internal\stockfish` folder, and its source is at https://github.com/official-stockfish/Stockfish.
