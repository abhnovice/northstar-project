ALTER TABLE tasks ADD COLUMN rescheduled INTEGER NOT NULL DEFAULT 0 CHECK (rescheduled IN (0, 1));

CREATE TABLE IF NOT EXISTS plan_days (
    date TEXT PRIMARY KEY,
    generated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO plan_days(date)
SELECT DISTINCT date FROM tasks WHERE manual=0;

CREATE TABLE IF NOT EXISTS task_reschedule_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    from_date TEXT NOT NULL,
    to_date TEXT NOT NULL,
    from_start_time TEXT NOT NULL,
    to_start_time TEXT NOT NULL,
    grouped INTEGER NOT NULL DEFAULT 0 CHECK (grouped IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_task_reschedule_history_task
    ON task_reschedule_history(task_id, created_at);
CREATE INDEX IF NOT EXISTS idx_tasks_rescheduled_date
    ON tasks(rescheduled, date);
