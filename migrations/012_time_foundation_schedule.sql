CREATE TABLE IF NOT EXISTS time_foundation_schedule (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    test_id INTEGER NOT NULL UNIQUE REFERENCES time_foundation_tests(id) ON DELETE CASCADE,
    planned_date TEXT NOT NULL,
    task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'PLANNED' CHECK (status IN ('PLANNED', 'COMPLETED', 'SKIPPED')),
    manual_override INTEGER NOT NULL DEFAULT 0 CHECK (manual_override IN (0, 1)),
    selection_reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_time_foundation_schedule_date
    ON time_foundation_schedule(planned_date, status);
CREATE INDEX IF NOT EXISTS idx_time_foundation_schedule_task
    ON time_foundation_schedule(task_id);
