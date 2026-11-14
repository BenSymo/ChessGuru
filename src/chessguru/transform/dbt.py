"""Run the dbt project that builds the gold layer from silver."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from chessguru.config import Settings
from chessguru.frozen import bundle_dir, dbt_command, is_frozen

# src/chessguru/transform/dbt.py -> repository (or /app in Docker) -> dbt/.
# The packaged app carries the dbt project inside its own folder.
DEFAULT_PROJECT_DIR = (
    bundle_dir() / "dbt" if is_frozen() else Path(__file__).resolve().parents[3] / "dbt"
)


class DbtError(Exception):
    """dbt could not run, or a model or test failed."""


@dataclass
class DbtResult:
    passed: int = 0
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def run_dbt(settings: Settings, command: str, project_dir: Path | None = None) -> DbtResult:
    """Run `dbt <command>` (e.g. build, docs generate) against the local database.

    dbt runs in its own process. dbt-duckdb keeps the database open for as long as
    its process lives, and DuckDB allows only one writer, so this makes sure the
    file is released as soon as dbt is done.

    dbt's own files (compiled SQL, logs, docs) go in the data folder, so the
    project folder stays clean and works when it is read-only (e.g. in Docker).
    """
    project = project_dir or settings.dbt_project_dir or DEFAULT_PROJECT_DIR
    if not (project / "dbt_project.yml").exists():
        raise DbtError(f"No dbt project found at {project}")

    target = settings.dbt_target_dir.resolve()
    args = [
        *dbt_command(),
        *command.split(),
        "--project-dir", str(project),
        "--profiles-dir", str(project),
        "--target-path", str(target),
        "--log-path", str((settings.data_dir / "dbt_logs").resolve()),
        "--no-send-anonymous-usage-stats",
        "--quiet",
    ]  # fmt: skip
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    results_file = target / "run_results.json"
    results_file.unlink(missing_ok=True)
    env = {
        **os.environ,
        "CHESSGURU_DB_PATH": str(settings.db_path.resolve()),
        "DO_NOT_TRACK": "1",
        "PYTHONUTF8": "1",  # Windows would otherwise use its old code page
    }
    process = subprocess.run(
        args, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
        check=False,
    )  # fmt: skip

    result = _summarise(results_file)
    if process.returncode != 0 and not result.failures:
        output = (process.stdout + process.stderr).strip().splitlines()
        detail = output[-1] if output else f"exit code {process.returncode}"
        raise DbtError(f"dbt {command} could not run: {detail}")
    return result


def _summarise(results_file: Path) -> DbtResult:
    result = DbtResult()
    if not results_file.exists():
        return result
    for node in json.loads(results_file.read_text()).get("results", []):
        status = node.get("status")
        name = node.get("unique_id", "?").split(".")[-1]
        if status in {"success", "pass"}:
            result.passed += 1
        elif status == "warn":
            result.warnings.append(f"{name}: {node.get('message')}")
        elif status != "skipped":
            result.failures.append(f"{name}: {node.get('message') or status}")
    return result
