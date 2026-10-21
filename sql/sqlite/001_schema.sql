-- SQLite mirror of sql/oracle/001_schema.sql, used by tests and local runs.
CREATE TABLE IF NOT EXISTS screening_run (
    run_id            TEXT PRIMARY KEY,
    started_at        TEXT NOT NULL,
    finished_at       TEXT,
    list_version      TEXT NOT NULL,
    threshold         REAL NOT NULL,
    records_screened  INTEGER NOT NULL,
    alerts_raised     INTEGER
);

CREATE TABLE IF NOT EXISTS screening_alert (
    alert_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id             TEXT NOT NULL REFERENCES screening_run(run_id),
    record_id          TEXT NOT NULL,
    entry_id           TEXT NOT NULL,
    matched_name       TEXT NOT NULL,
    name_type          TEXT NOT NULL CHECK (name_type IN ('primary', 'alias')),
    name_score         REAL NOT NULL,
    score              REAL NOT NULL,
    model_probability  REAL,
    status             TEXT NOT NULL CHECK (status IN ('OPEN', 'AUTO_CLOSED')),
    UNIQUE (run_id, record_id, entry_id)
);

CREATE INDEX IF NOT EXISTS ix_alert_status ON screening_alert (run_id, status);
