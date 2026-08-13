CREATE TABLE IF NOT EXISTS task_resource_assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    resource_id TEXT NOT NULL REFERENCES study_resources(id),
    stage TEXT NOT NULL CHECK (stage IN ('LEARN', 'PRACTICE', 'PYQ')),
    stage_order INTEGER NOT NULL DEFAULT 0,
    estimated_minutes INTEGER NOT NULL DEFAULT 0,
    target_count INTEGER NOT NULL DEFAULT 0,
    accuracy_target REAL NOT NULL DEFAULT 0,
    selected_reason TEXT NOT NULL DEFAULT '',
    manual_override INTEGER NOT NULL DEFAULT 0 CHECK (manual_override IN (0, 1)),
    completed INTEGER NOT NULL DEFAULT 0 CHECK (completed IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(task_id, stage)
);

CREATE TABLE IF NOT EXISTS task_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL UNIQUE REFERENCES tasks(id) ON DELETE CASCADE,
    attempted INTEGER NOT NULL DEFAULT 0 CHECK (attempted >= 0),
    correct INTEGER NOT NULL DEFAULT 0 CHECK (correct >= 0 AND correct <= attempted),
    time_spent INTEGER NOT NULL DEFAULT 0 CHECK (time_spent >= 0),
    confidence INTEGER NOT NULL DEFAULT 3 CHECK (confidence BETWEEN 1 AND 5),
    accuracy REAL NOT NULL DEFAULT 0,
    average_time REAL NOT NULL DEFAULT 0,
    notes TEXT NOT NULL DEFAULT '',
    completed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_task_resource_assignments_task
    ON task_resource_assignments(task_id, stage_order);
CREATE INDEX IF NOT EXISTS idx_task_resource_assignments_resource
    ON task_resource_assignments(resource_id);
CREATE INDEX IF NOT EXISTS idx_task_results_task ON task_results(task_id);
