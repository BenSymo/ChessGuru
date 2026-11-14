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

- Move labels by drop in winning chances: inaccuracy `?!` > 10%, mistake `?` > 20%, blunder `??` > 30%.
- Accuracy from winning chances; game phase (opening, middlegame, endgame).
- Mistake tags: hanging piece, missed fork/pin/skewer, missed or allowed mate,
  failed to convert +3, low-clock blunder.

## Tips

Each tip rule reads a gold table and checks it against a limit. Tips are ranked by how many games
they cost you, show how many games they are based on, and include up to 3 example positions.

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
