# ChessGuru

See where you're going wrong at chess, and what to fix first to reach the next level.

ChessGuru downloads your games from chess.com and checks every move with Stockfish (a chess
engine). It then ranks your biggest weaknesses by how many games' worth of points each one
costs you, with example positions from your own games. Everything runs on your own computer.

**New to the code?** Read [How ChessGuru works](docs/HOW_IT_WORKS.md).

## Windows: download and run

Nothing else to install: Python and Stockfish are inside the app.

1. Download **ChessGuru-Setup.exe**.
   - **From a release:** the [Releases page](https://github.com/BenSymo/ChessGuru/releases).
   - **Before the first release:** open the newest successful **Windows app** run under the repository's **Actions** tab and download it from its **Artifacts** section.
2. Run it. If Windows says *"Windows protected your PC"* (the app isn't signed), click **More info**, then **Run anyway**.
3. Open **ChessGuru** from the Start menu or the desktop shortcut.
   - A window opens to show it's running, and the dashboard opens in your browser.
   - Close that window to stop ChessGuru.

**Things to know:**
- **Where your data goes:** games and settings are kept in `%LOCALAPPDATA%\ChessGuru`. To change a setting, put a `.env` file there (see [Settings](#settings)).
- **Older PCs:** the bundled Stockfish needs a CPU from about 2013 or newer (AVX2).
- **No-install option:** **ChessGuru-portable.zip** is the same app. Unzip it anywhere and run `ChessGuru.exe`.

## Run from source (Windows, macOS, Linux)

You need:
- [uv](https://docs.astral.sh/uv/), which also installs Python 3.12+ for you
- [Stockfish](https://stockfishchess.org/download/)
  - **macOS:** `brew install stockfish`
  - **Ubuntu/Debian:** `sudo apt install stockfish`
  - **Windows:** download it from stockfishchess.org, then set `CHESSGURU_STOCKFISH_PATH` in `.env`

```bash
git clone https://github.com/BenSymo/ChessGuru.git
cd ChessGuru
uv sync
cp .env.example .env        # then set CHESSGURU_USERNAME and CHESSGURU_CONTACT
uv run chessguru doctor     # checks your settings and that Stockfish works
uv run chessguru dashboard  # opens the dashboard in your browser
```

## Using the dashboard

**First time:** enter your chess.com username and press **Get my games**. It downloads your newest
games, analyses them (about 2–3 seconds per game), and builds your stats.

**Sidebar:**
- **Filters:** time control, colour and rated games only.
- **Games to include:** how many of your newest games the pages cover (default 30).
- **Analyse these games:** analyses any of the shown games that aren't analysed yet.
- **Get new games from chess.com:** downloads and analyses anything new.

| Page | What it shows |
|---|---|
| Overview | Your top 3 things to fix, then score, accuracy, where and why your bad moves happen, rating |
| Tips | Every tip, ranked by what it cost you, with example positions from your games |
| Openings | Results per opening family as White and as Black |
| Mistakes | Accuracy per game phase, reasons for bad moves, your costliest moves |
| Time | Time per move, bad moves by clock left, losses on time |
| Endgames | Converting winning positions, endgame accuracy, how your games finish |
| Game viewer | Step through any game on a board, with Stockfish's verdict and a win-chance chart |
| Data health | What the pipeline did, games it set aside, row counts |

**Reading the numbers:**
- **Move labels:** a move is an *inaccuracy*, *mistake* or *blunder* when it lowers your chance of winning by 5, 10 or 15+ points (Lichess's thresholds).
- **Tip cost:** roughly how many games' worth of points a problem cost you.
- **Clear pattern vs early sign:** a *clear pattern* showed up in 3+ games out of 15+. An *early sign* needs more games to confirm.

## Command line

Replace `<you>` with your chess.com username, or set `CHESSGURU_USERNAME` and leave it out.
In the Windows app, use `ChessGuru.exe <command>` instead of `uv run chessguru <command>`.

| Command | What it does |
|---|---|
| `uv run chessguru run <you>` | Everything: download, check, analyse, build the tables |
| `uv run chessguru run <you> --games 100` | The same, for your newest 100 games |
| `uv run chessguru tips <you>` | Print what to fix first |
| `uv run chessguru dashboard` | Open the dashboard |
| `uv run chessguru fetch <you>` | Just download and check games |
| `uv run chessguru analyse <you> --depth 18` | Just the Stockfish step (deeper = slower, more accurate) |
| `uv run chessguru build` | Just rebuild the tables the dashboard reads (with dbt) |
| `uv run chessguru doctor` | Check settings and that Stockfish works |

Analysis is saved, so asking for more games only analyses the extra ones. Games are only analysed again if you ask for a greater depth.

## Settings

Put these in `.env` (copy [`.env.example`](.env.example)). In the Windows app, put it in
`%LOCALAPPDATA%\ChessGuru\.env`.

| Setting | Default | What it does |
|---|---|---|
| `CHESSGURU_USERNAME` | none | Your chess.com username |
| `CHESSGURU_CONTACT` | none | Your email or a link. Chess.com asks apps to include contact details |
| `CHESSGURU_MAX_GAMES` | `30` | How many of your newest games to analyse and show |
| `CHESSGURU_ENGINE_DEPTH` | `14` | Stockfish search depth |
| `CHESSGURU_DATA_DIR` | `./data` | Where games and the database are stored |
| `CHESSGURU_STOCKFISH_PATH` | found automatically | Path to Stockfish, if it isn't found |

## Privacy

- **Local only:** your games and results stay on your computer. The only site contacted is `api.chess.com`.
- **Opponents' names:** not stored. Only the raw files downloaded from chess.com contain them, exactly as chess.com sent them.
- **Kept out of git:** the data folder and `.env` are never committed.

## Docker

The image includes Stockfish.

```bash
docker build -t chessguru .
```
```bash
docker run --rm --env-file .env -v "$PWD/data:/app/data" -p 8501:8501 chessguru dashboard
```

## Development

```bash
uv run ruff check .      # lint
uv run ruff format .     # format
uv run mypy src tests    # type check (strict)
uv run pytest            # tests with coverage
```

**CI** runs all of these on every push, then builds the Docker image. A separate workflow builds and
tests the Windows app. To publish a release, push a version tag:

```bash
git tag v0.1.0
```
```bash
git push origin v0.1.0
```

**How the data is handled:**
- raw files, then cleaned tables, then the tables the dashboard reads (bronze / silver / gold)
- a data contract and quality checks; bad games are set aside, not silently dropped
- dbt builds the dashboard's tables and tests them on every run
- a log of every pipeline run

See [How ChessGuru works](docs/HOW_IT_WORKS.md) for the details.

## Licence notes

Stockfish is free software under the GPL v3. The Windows app ships its licence in
`_internal\stockfish`, and its source is at https://github.com/official-stockfish/Stockfish.
