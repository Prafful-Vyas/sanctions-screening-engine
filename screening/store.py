"""Persistence for runs and alerts over a DB-API connection.

All statements use named binds (`:name`), which both python-oracledb and sqlite3
accept, so the same SQL runs against Oracle in production and SQLite in tests.
DDL is dialect-specific and lives in sql/oracle and sql/sqlite.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .engine import Match

INSERT_RUN = """
INSERT INTO screening_run (run_id, started_at, list_version, threshold, records_screened)
VALUES (:run_id, :started_at, :list_version, :threshold, :records_screened)
"""

INSERT_ALERT = """
INSERT INTO screening_alert (run_id, record_id, entry_id, matched_name, name_type,
                             name_score, score, model_probability, status)
VALUES (:run_id, :record_id, :entry_id, :matched_name, :name_type,
        :name_score, :score, :model_probability, :status)
"""

FINISH_RUN = """
UPDATE screening_run SET finished_at = :finished_at, alerts_raised = :alerts_raised
WHERE run_id = :run_id
"""


def connect_sqlite(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    ddl = (Path(__file__).resolve().parent.parent / "sql" / "sqlite" / "001_schema.sql").read_text()
    conn.executescript(ddl)
    return conn


def connect_oracle(dsn: str, user: str, password: str):  # pragma: no cover - needs Oracle
    import oracledb  # optional dependency: pip install .[oracle]

    return oracledb.connect(user=user, password=password, dsn=dsn)


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def start_run(conn, run_id: str, list_version: str, threshold: float, records: int) -> None:
    conn.cursor().execute(INSERT_RUN, {
        "run_id": run_id, "started_at": now(), "list_version": list_version,
        "threshold": threshold, "records_screened": records,
    })


def save_alerts(conn, run_id: str, alerts: list[tuple[Match, float | None, str]]) -> None:
    rows = [{
        "run_id": run_id, "record_id": m.record_id, "entry_id": m.entry_id,
        "matched_name": m.matched_name, "name_type": m.name_type,
        "name_score": m.name_score, "score": m.score,
        "model_probability": prob, "status": status,
    } for m, prob, status in alerts]
    if rows:
        conn.cursor().executemany(INSERT_ALERT, rows)


def finish_run(conn, run_id: str, alerts_raised: int) -> None:
    conn.cursor().execute(FINISH_RUN, {
        "run_id": run_id, "finished_at": now(), "alerts_raised": alerts_raised,
    })
    conn.commit()
