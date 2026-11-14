# How ChessGuru works

A guide for anyone reading or changing the code. For installing and using the app, see the
[README](../README.md).

## The big picture

ChessGuru is a small data pipeline with a dashboard on top. Everything runs on your own
computer and is stored in one folder (`data/`, or `%LOCALAPPDATA%\ChessGuru` in the Windows app).

```
chess.com API
    │  fetch      ingest/      download month files, politely
    ▼
BRONZE  data/bronze/<user>/<YYYY-MM>.json      raw files, exactly as sent
    │  check      quality/     data contract + checks; bad games → quarantine table
    │  parse      parse/       PGN → one row per game and per move; opponent name hashed
    ▼
SILVER  silver_games, silver_moves             (DuckDB: data/chessguru.duckdb)
    │  analyse    analysis/    Stockfish scores every position; label + tag every move
    ▼
SILVER  silver_move_evals, silver_game_analysis
    │  build      transform/ + dbt/   staging → intermediate → star schema, with tests
    ▼
GOLD    fact_game, fact_move, dim_*
    │             app/data.py   read-only queries
    ▼
DASHBOARD (Streamlit)  app/          filters, charts, tips (insights/tips.py)
```

Every step is a function in [`pipeline.py`](../src/chessguru/pipeline.py). The command line
(`cli.py`) and the dashboard's update buttons (`app/main.py`) both call those same functions.
Each step writes a row to the `pipeline_runs` table, saying whether it worked and what it did.

`chessguru run <user>` runs fetch → check → parse → analyse → build in order.

## Folder map

| Path | What's there |
|---|---|
| `src/chessguru/cli.py` | The `chessguru` command (Typer): `run`, `fetch`, `analyse`, `build`, `tips`, `dashboard`, `doctor`, `docs`, `version` |
| `src/chessguru/config.py` | Settings (`CHESSGURU_*` environment variables or `.env`), and finding Stockfish |
| `src/chessguru/pipeline.py` | The pipeline steps, each logged to `pipeline_runs` |
| `src/chessguru/db.py` | DuckDB connection, silver table definitions, schema version, run log |
| `src/chessguru/api/` | chess.com client (`client.py`) and the data contract (`contracts.py`) |
| `src/chessguru/ingest/` | Bronze file store and the "which months to download" logic |
| `src/chessguru/quality/` | Data quality checks |
| `src/chessguru/parse/` | PGN → silver rows (`games.py`), and writing them (`silver.py`) |
| `src/chessguru/governance/` | Hashing opponent usernames |
| `src/chessguru/analysis/` | Stockfish (`engine.py`), scoring maths (`scoring.py`), game phases, tactic tags, per-game analysis, and running it in parallel (`store.py`) |
| `src/chessguru/transform/` | Runs dbt |
| `src/chessguru/insights/tips.py` | The tip rules |
| `src/chessguru/app/` | The Streamlit dashboard: `main.py` (entry, sidebar, navigation), `data.py` (queries), `aggregates.py` (summaries), `charts.py`, `board.py`, `components.py`, and one file per page in `views/` |
| `src/chessguru/frozen.py` | Extra start-up logic for the packaged Windows app |
| `dbt/` | The dbt project that builds gold from silver |
| `tests/` | pytest tests (fake API, fake engine, sample games) |
| `packaging/` | PyInstaller recipe and Inno Setup installer script for the Windows app |
| `.github/workflows/` | CI (`ci.yml`) and the Windows app build (`windows-app.yml`) |

## Each step in detail

### 1. Fetch (bronze)

- **API used:** chess.com's free Published-Data API. It needs no key.
  - It lists which months a player has games in.
  - Each month's games come as one JSON file.
- **Being polite:** the client (`api/client.py`) sends a User-Agent with your contact details (`CHESSGURU_CONTACT`) and makes one request at a time.
- **Retries:** it retries rate limits (429) and server errors with growing waits, and follows `Retry-After`.
- **Unknown player:** a 404 means there's no such player.
- **How much is downloaded:** months are fetched newest first, until there are at least `max_games` games.
- **Storage:** each month is saved as-is in `data/bronze/<user>/<YYYY-MM>.json`. The file is written to a temporary file first and then renamed, so a crash never leaves half a file.
- **Reusing files:** a stored month is reused only if it was downloaded *after that month ended* (`BronzeStore.is_complete`). It checks the file's modified time. Anything else is downloaded again, both the current month and a past month first downloaded mid-month.

### 2. Check (data quality)

`quality/checks.py` runs over every stored month. It doesn't trust the raw data.

| Check | Fails when | Action |
|---|---|---|
| Readable | Month file isn't valid JSON with a `games` list | quarantine the file |
| Contract | A game doesn't match the pydantic model in `api/contracts.py` (missing field, wrong type, unknown time class) | quarantine the game |
| Unique | Same game UUID twice | quarantine the duplicate |
| Standard chess | Variant (e.g. Chess960) or custom start position | quarantine |
| Right player | The user isn't one of the two players | quarantine |
| Too many broken | More than 50% of games break the contract (chess.com probably changed its format) | **stop** with `DataContractError` |
| Fresh | Newest game is over 30 days old | warn |

- **Where set-aside games go:** the `quarantine` table, with the reason and the step (`check` or `parse`).
- **Re-running:** each step replaces its own rows, so re-running never duplicates them.

### 3. Parse (silver)

`parse/games.py` turns each valid game into:

- **one `silver_games` row**, seen from the analysed player's side. It holds:
  - colour, ratings
  - result and outcome (`win` / `draw` / `loss`), and the end reason (from the loser's code, e.g. `resigned`, `timeout`)
  - time control, split into base and increment seconds
  - the opening name and family, read from chess.com's opening URL
  - the PGN
- **one `silver_moves` row per ply** (half-move). It holds:
  - SAN and UCI
  - the piece moved
  - capture / check / castle / promotion flags
  - the position before the move (FEN)
  - the clock after the move, and the time spent (`previous clock + increment − clock`)
  - daily games have no clock data

Games already in silver are skipped. If the PGN can't be read, the game is quarantined
(step `parse`).

**Opponent names:** the raw opponent username is kept only in silver. A 16-character HMAC-SHA256 hash
(`opponent_key`) is what goes further (see Privacy).

**Schema changes:** if the silver tables change shape, bump `SCHEMA_VERSION` in `db.py`. On the next run,
older silver tables are dropped and rebuilt from bronze, which is always kept.

### 4. Analyse (Stockfish)

`analysis/` scores every position in a game, then judges every move.

- **Which games:** the newest `max_games` games that aren't yet analysed at this depth or deeper.
  - The dashboard can pass `only=[...]` to analyse just the games it is showing.
- **Running in parallel:**
  - One Stockfish process per worker thread: CPU cores − 1, at most 8.
  - Each game is saved as soon as it's done, so stopping part-way loses nothing.
  - If a game fails, the queued ones are cancelled.
- **Scoring:** formulas match Lichess (`scoring.py`).
  - **Win chance** (0–100) from centipawns `cp`, capped at ±1000: `50 + 50·(2/(1+e^(−0.00368208·cp)) − 1)`. Mate = 100 or 0.
  - **Drop** = win chance before the move − after it, from the mover's side.
  - **Label:** inaccuracy at 5+ points, mistake at 10+, blunder at 15+. Otherwise "best" if it was the engine's move, or "good".
  - **Move accuracy** = `103.1668·e^(−0.04354·drop) − 3.1669`, kept between 0 and 100.
  - **Game accuracy** = the average of the arithmetic and harmonic means of move accuracies. The harmonic mean makes blunders count.
- **Phase** (`phase.py`):
  - **Opening** until after move 12, or until 10 or fewer pieces remain (not counting pawns and kings).
  - **Endgame** at 6 or fewer pieces.
  - Phases only move forward.
- **Tags** (why a bad move was bad, `game.py` + `tactics.py`). These are simple checks, not a full tactics engine; many bad moves get no tag.

  | Tag | Meaning |
  |---|---|
  | `hanging_piece` | The opponent's best reply wins a piece, either undefended or of higher value than the capturer |
  | `missed_fork` / `missed_pin` / `missed_skewer` | The engine's move made that tactic and yours didn't |
  | `missed_mate` | You had a forced mate and lost it. Also given to inaccuracies |
  | `allowed_mate` | Your move let the opponent force mate |
  | `missed_punish` | The opponent's previous move was a mistake or blunder, and you didn't take advantage |
  | `low_clock` | You were under 10% of your starting time. Added later, in dbt |

- **Results:** stored in `silver_move_evals` (one row per move, both sides) and `silver_game_analysis` (depth and accuracy per game).

### 5. Build (gold, with dbt)

`transform/dbt.py` runs `dbt build`, which builds every model and runs every test.

**How dbt is run:**
- **Separate process:** dbt runs in a process of its own because DuckDB allows only one writer, and dbt keeps its connection open until its process ends.
- **Database path:** passed in as `CHESSGURU_DB_PATH`.
- **Output:** dbt's own files (compiled SQL, logs, docs) go in the data folder.
- **Results:** the outcome is read from `run_results.json`.

| Layer | Models | Notes |
|---|---|---|
| staging (views) | `stg_games`, `stg_moves`, `stg_move_evals`, `stg_game_analysis` | Clean names and types. Adds `score` (1 / ½ / 0). The raw opponent name is dropped here |
| intermediate (views) | `int_player_move_evals`, `int_game_eval_stats`, `int_rating_changes` | Player's own moves plus `low_clock`. Per-game bad-move counts and peak win chance. Rating change points |
| gold (tables) | `fact_game`, `fact_move`, `dim_date`, `dim_time_control`, `dim_opening`, `dim_opponent`, `dim_player` | Star schema. See below |

**The star schema:**
- **`fact_game`:** one row per game.
  - Keys to each dimension.
  - Outcome, score and ratings.
  - Analysis results: `is_analysed`, `engine_accuracy`, blunders / mistakes / inaccuracies, `peak_win_chance`.
  - `failed_to_convert`: reached 75%+ win chance and didn't win.
  - `recency_rank`: 1 = newest.
- **`fact_move`:** one row per ply. Both sides are included; `is_player_move` marks yours.
- **`dim_player`:** a Type 2 slowly changing dimension. There's a new row each time your rating changes in a time class, with `valid_from` and `valid_to`, so rating history is kept.
- **`dim_opponent`:** opponents are known only by their hash key.
- **Keys:** made with the `surrogate_key` macro (an md5 of the columns).

**Tests:**
- **Generic tests** in the `_*.yml` files check that keys are unique and not null, and that facts point at real dimension rows.
- **Custom tests** in `dbt/tests/` check that:
  - every silver game reaches `fact_game`
  - each player has one current `dim_player` row per time class
  - no raw opponent username appears in gold
  - scores and win chances stay in range
  - every evaluation belongs to a move

**Schema names:** a custom `generate_schema_name` macro makes the schema names exactly `staging`,
`intermediate` and `gold`.

### 6. Tips (`insights/tips.py`)

**What goes in:** the games the dashboard is showing, after the sidebar filters. **What comes out:** a ranked list of tips.

**What a tip contains:**
- **`cost`:** roughly how many games' worth of points the problem cost.
  - For move patterns: the win-chance drop of the matching bad moves, summed per game, capped at 1 per game, divided by 100.
  - For results patterns (openings, colour, tilt): points below what you'd otherwise expect.
- **`based_on`**, and **`games_affected`**: the problem must appear in at least 2 games.
- **"Clear pattern" or "early sign":** clear means 3+ games affected out of 15+.
- **Up to 3 examples:** positions or games. Examples already shown by a higher-ranked tip are skipped where possible.

**The rules:**

| Rule | Fires when |
|---|---|
| `tag_tips` | One tip per tag group (hanging pieces, missed tactics, missed mates, allowed mates, missed punish, time trouble) seen in 2+ games |
| `phase_tips` | One phase's accuracy is 3+ points below the others (a fix) or above them (a strength). The cost counts only what that phase loses beyond your usual rate, so it doesn't double-count the tag tips |
| `conversion_tips` | You reached a winning position (75%+) but didn't win in 2+ games. A strength if you convert 90%+ of 5+ winning games |
| `opening_tips` | An opening family scores under 40% (fix) or 65%+ (strength), in at least max(3, 10% of games) games |
| `time_loss_tips` | 2+ losses on time while the position was still playable (win chance 40%+) |
| `tilt_tips` | Your score in games played within an hour of a loss is 15+ points below your overall score (needs 10+ games, 5+ after a loss) |
| `colour_tips` | Your score with one colour is 20+ points below the other (5+ games each) |

**Order:** fixes are sorted by cost, then strengths are listed.

**Adding a rule:** write a function `(games, moves) -> list[Tip]`, add it to `RULES`, and add a test in `tests/test_tips.py`.

### 7. Dashboard (`app/`)

`chessguru dashboard` starts Streamlit on `app/main.py`.

**On each page load, `main.py`:**
1. Shows the **first-run form** if there's no data yet.
2. Otherwise draws the **sidebar**: player, time controls, colour, rated only, and **games to include** (newest N).
3. Loads the filtered games and the player's analysed moves (`data.py`).
   - Connections are read-only and short-lived, so the pipeline can write in between.
   - Results are cached until the database file changes.
4. Puts it all in a `Context` (`context.py`) that every page reads.
5. Shows the **update buttons**: "Analyse these games" (only the shown games not yet analysed) and "Get new games from chess.com" (the whole pipeline).
6. Runs the chosen page from `views/`.

**Where the work happens:**
- Calculations are in `aggregates.py` and `insights/tips.py`. These are plain pandas with no Streamlit, so they're unit tested.
- Pages in `views/` only lay things out.
- Charts (`charts.py`) use a colour-blind-checked palette, with separate light and dark themes that follow the viewer's setting.
- Boards are SVG drawn with python-chess (`board.py`). The played move is a red or blue arrow; the engine's move is green.

**Adding a page:** add `views/<name>.py` with a `render()` function, and add it to the `pages` dict in `main.py`.

## Data and privacy

- **Local only:** everything stays on your computer. The only network calls are to `api.chess.com`.
- **Opponent names:**
  - Opponent usernames are hashed with HMAC-SHA256 before gold, using `CHESSGURU_HASH_KEY`, or else a random key created once in `<data>/.hash_key`.
  - The same opponent always gets the same key, but the name can't be recovered without the key.
  - Deleting the key file changes every key. Delete the database too so they're rebuilt consistently.
- **Excluded from git:** `data/` and `.env` are never committed (`.gitignore`).
- **Starting again:** delete the data folder and run again. Bronze is the only thing that needs downloading again.

## Settings

All settings are read from `CHESSGURU_*` environment variables or a `.env` file
(`config.py`, see `.env.example`):

| Setting | Default | |
|---|---|---|
| `USERNAME` | none | Default player for commands |
| `CONTACT` | none | Your email or a link, sent in the User-Agent as chess.com asks |
| `DATA_DIR` | `./data` (`%LOCALAPPDATA%\ChessGuru` in the Windows app) | Where everything is stored |
| `STOCKFISH_PATH` | auto | Otherwise: the bundled copy (Windows app), then `stockfish` on PATH, then common install folders |
| `ENGINE_DEPTH` | 14 | Higher is slower and more accurate. About 2–3 s per game at 14 on 4 cores |
| `MAX_GAMES` | 30 | Default number of newest games to fetch, analyse and show |
| `HASH_KEY` | generated | Key for opponent hashes |

## The Windows app

**What's in it:** `packaging/chessguru.spec` (PyInstaller) bundles:
- Python and every library
- the dashboard files
- the dbt project
- `stockfish.exe`

It makes a folder, `dist/ChessGuru/`, with `ChessGuru.exe` inside. `packaging/installer.iss` (Inno Setup) wraps that folder into `ChessGuru-Setup.exe`. It installs per user, so no admin rights are needed.

**What changes in the packaged app** (see `frozen.py`):
- **Double-click:** starting `ChessGuru.exe` with no arguments opens the dashboard.
- **dbt:** runs by starting the exe again with the hidden argument `__dbt__`.
- **Data and settings:** live in `%LOCALAPPDATA%\ChessGuru`. A `.env` file there is also read.
- **Stockfish:** the bundled copy is used.

**Build workflow:** `.github/workflows/windows-app.yml` builds it on Windows on every relevant push, then:
1. runs `version`, `doctor` (which starts Stockfish) and a gold `build`
2. starts the dashboard and checks it responds
3. builds the installer, and uploads both the installer and a portable zip as artifacts

Pushing a tag such as `v0.1.0` also publishes them as a GitHub release.

## Testing and CI

**Running the tests:** `uv run pytest` (with coverage). No network is needed. The two tests that use real Stockfish are skipped if it isn't installed.

**Stand-ins the tests use:**
- **Fake chess.com:** the API is faked with `respx`.
- **Fake engine:** `tests/fake_engine.py` scores positions by material.
- **Sample games:** built in `tests/factories.py`.
- **Sample gold database:** one is built once per test session (`tests/conftest.py`) for the dbt, dashboard and tips tests.

**Dashboard tests:** pages are rendered headlessly with Streamlit's `AppTest`.

**`ci.yml`:**
1. ruff (lint and format check), mypy (strict) and pytest
2. builds the Docker image and runs `doctor` in it

## Things to know when changing the code

- **DuckDB is single-writer.** Open a connection, do the work, close it. The dashboard only
  opens read-only connections. A "database is busy" message means another step is writing.
- **Silver changes:** bump `SCHEMA_VERSION` in `db.py` whenever a silver table changes shape.
- **New silver columns:** reach gold only if you add them to the staging and fact models in `dbt/`.
- **Pipeline steps:** `pipeline.py` is the single place they live. Keep the CLI and dashboard thin.
- **Code style:** ruff and mypy (strict) must pass. CI enforces it.
