# ChessGuru plan

**Goal:** quickly see where you're going wrong and what to fix first to reach the next level.
Light by design: only your own games, stored on your machine. The last 30 games are analysed by default.

## Data flow

```
chess.com API → Fetcher → Bronze (raw JSON) → Checks → Silver (games, moves)
  → Stockfish analysis → Gold (dbt star schema) → Tip rules → Streamlit dashboard
                                    ↓
                               Quarantine (bad games)
```

Airflow runs the steps daily in full-stack mode. Lite mode runs the same steps from the CLI.

## Tools

| Tool | Use |
|---|---|
| Docker | App image with Stockfish; Compose for Airflow + Streamlit |
| Unit testing | pytest, sample PGN fixtures, fake API (respx), fake engine |
| Data modelling | Bronze / silver / gold; star schema; Type 2 rating history |
| dbt (DuckDB) | Staging, intermediate and mart models with tests and lineage |
| Data quality | pydantic API contract; completeness, duplicates, validity, freshness; quarantine |
| CI/CD | GitHub Actions: ruff, mypy, pytest, dbt build, Docker build |
| Governance | Secrets in .env; opponent names hashed (HMAC); retention; run logs |
| Airflow | Daily DAG with retries (full-stack mode) |

## Analysis

- Move labels by drop in winning chances (Lichess thresholds): inaccuracy `?!` 5+ points,
  mistake `?` 10+, blunder `??` 15+.
- Accuracy from winning chances; game phase (opening, middlegame, endgame).
- Mistake tags: hanging piece, missed fork/pin/skewer, missed or allowed mate, missed punish,
  low-clock blunder; per game: failed to convert (75%+ win chance, about +3, but no win).
- The number of games analysed is changeable (`--games`, `CHESSGURU_MAX_GAMES`, and later the
  dashboard); results are cached so only new games are analysed.

## Tips

Each tip rule checks a pattern in the filtered games and analysed moves (src/chessguru/insights).
Tips are ranked by cost (games' worth of points lost), show how many games they are based on
(clear pattern vs early sign), and include up to 3 example positions, preferring ones not already
shown by a higher tip. The weak-phase tip counts only the cost beyond your usual rate elsewhere.

## Dashboard pages

Overview (3 biggest leaks first) · Openings · Mistakes · Time Management · Endgames · Tips ·
Game Viewer · Data Health

## Milestones

1. Project setup: uv, ruff, pytest, CI, Dockerfile, .env config
2. API client, bronze storage, data contracts, quarantine
3. Silver parsing of games and moves
4. dbt gold models and tests
5. Stockfish analysis, move labels, phases, mistake tags
6. Dashboard pages
7. Tip rules, Tips page, Game Viewer
8. Airflow DAG + Docker Compose
9. Governance polish + README
