-- Oracle 19c+ schema for screening runs and alerts.
-- Alerts are range-partitioned by month of the run so that retention (e.g. keep 7
-- years, then purge) is a partition drop rather than a multi-million-row DELETE.

CREATE TABLE screening_run (
    run_id            VARCHAR2(64)   NOT NULL,
    started_at        TIMESTAMP      NOT NULL,
    finished_at       TIMESTAMP,
    list_version      VARCHAR2(64)   NOT NULL,
    threshold         NUMBER(5,4)    NOT NULL,
    records_screened  NUMBER(12)     NOT NULL,
    alerts_raised     NUMBER(12),
    CONSTRAINT pk_screening_run PRIMARY KEY (run_id)
);

CREATE TABLE screening_alert (
    alert_id           NUMBER GENERATED ALWAYS AS IDENTITY,
    run_id             VARCHAR2(64)   NOT NULL,
    record_id          VARCHAR2(64)   NOT NULL,
    entry_id           VARCHAR2(64)   NOT NULL,
    matched_name       VARCHAR2(400)  NOT NULL,
    name_type          VARCHAR2(10)   NOT NULL,
    name_score         NUMBER(5,4)    NOT NULL,
    score              NUMBER(6,4)    NOT NULL,
    model_probability  NUMBER(7,6),
    status             VARCHAR2(12)   NOT NULL,
    created_at         TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_screening_alert PRIMARY KEY (alert_id, created_at),
    CONSTRAINT fk_alert_run FOREIGN KEY (run_id) REFERENCES screening_run (run_id),
    CONSTRAINT ck_alert_name_type CHECK (name_type IN ('primary', 'alias')),
    CONSTRAINT ck_alert_status CHECK (status IN ('OPEN', 'AUTO_CLOSED')),
    CONSTRAINT uq_alert UNIQUE (run_id, record_id, entry_id, created_at)
)
PARTITION BY RANGE (created_at) INTERVAL (NUMTOYMINTERVAL(1, 'MONTH'))
(PARTITION p_initial VALUES LESS THAN (TIMESTAMP '2026-01-01 00:00:00'));

CREATE INDEX ix_alert_status ON screening_alert (run_id, status) LOCAL;

-- Analysts only see alerts; they never write to them directly.
-- GRANT SELECT ON screening_alert TO screening_analyst_role;
-- GRANT SELECT ON screening_run   TO screening_analyst_role;
