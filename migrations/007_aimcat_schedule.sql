CREATE TABLE IF NOT EXISTS aimcat_schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL DEFAULT 'TIME',
    series TEXT NOT NULL DEFAULT 'AIMCAT',
    test_ref TEXT NOT NULL UNIQUE,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    preferred_attempt_date TEXT NOT NULL,
    planned_attempt_date TEXT,
    actual_attempt_date TEXT,
    status TEXT NOT NULL DEFAULT 'UPCOMING'
        CHECK (status IN ('PAST','UPCOMING','AVAILABLE','PLANNED','COMPLETED','MISSED','ANALYSIS_DUE')),
    historical INTEGER NOT NULL DEFAULT 0 CHECK (historical IN (0, 1)),
    skipped INTEGER NOT NULL DEFAULT 0 CHECK (skipped IN (0, 1)),
    converted_to_additional INTEGER NOT NULL DEFAULT 0 CHECK (converted_to_additional IN (0, 1)),
    manual_override INTEGER NOT NULL DEFAULT 0 CHECK (manual_override IN (0, 1)),
    analysis_completed INTEGER NOT NULL DEFAULT 0 CHECK (analysis_completed IN (0, 1)),
    resolve_completed INTEGER NOT NULL DEFAULT 0 CHECK (resolve_completed IN (0, 1)),
    mock_id INTEGER UNIQUE REFERENCES mocks(id),
    diagnosis_json TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (start_date <= end_date),
    CHECK (planned_attempt_date IS NULL OR converted_to_additional=1 OR (planned_attempt_date >= start_date AND planned_attempt_date <= end_date)),
    CHECK (actual_attempt_date IS NULL OR converted_to_additional=1 OR (actual_attempt_date >= start_date AND actual_attempt_date <= end_date))
);

ALTER TABLE tasks ADD COLUMN aimcat_schedule_id INTEGER REFERENCES aimcat_schedules(id);
ALTER TABLE tasks ADD COLUMN archived INTEGER NOT NULL DEFAULT 0 CHECK (archived IN (0, 1));

ALTER TABLE mocks ADD COLUMN aimcat_schedule_id INTEGER REFERENCES aimcat_schedules(id);
ALTER TABLE mocks ADD COLUMN varc_incorrect INTEGER NOT NULL DEFAULT 0;
ALTER TABLE mocks ADD COLUMN dilr_incorrect INTEGER NOT NULL DEFAULT 0;
ALTER TABLE mocks ADD COLUMN qa_incorrect INTEGER NOT NULL DEFAULT 0;
ALTER TABLE mocks ADD COLUMN time_waste_questions INTEGER NOT NULL DEFAULT 0;
ALTER TABLE mocks ADD COLUMN poor_dilr_selections INTEGER NOT NULL DEFAULT 0;
ALTER TABLE mocks ADD COLUMN guessing_errors INTEGER NOT NULL DEFAULT 0;
ALTER TABLE mocks ADD COLUMN topics_involved TEXT NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_aimcat_window ON aimcat_schedules(start_date, end_date);
CREATE INDEX IF NOT EXISTS idx_aimcat_planned ON aimcat_schedules(planned_attempt_date, historical, skipped);
CREATE INDEX IF NOT EXISTS idx_tasks_aimcat ON tasks(aimcat_schedule_id, archived, date);
CREATE UNIQUE INDEX IF NOT EXISTS idx_mocks_aimcat ON mocks(aimcat_schedule_id) WHERE aimcat_schedule_id IS NOT NULL;
