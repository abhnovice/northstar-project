ALTER TABLE tasks ADD COLUMN completed_early INTEGER NOT NULL DEFAULT 0 CHECK (completed_early IN (0, 1));
ALTER TABLE tasks ADD COLUMN original_planned_date TEXT;
ALTER TABLE tasks ADD COLUMN actual_completion_date TEXT;
ALTER TABLE tasks ADD COLUMN reallocated_task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL;
ALTER TABLE tasks ADD COLUMN reallocated_from_date TEXT;
ALTER TABLE tasks ADD COLUMN reallocated_to_date TEXT;
ALTER TABLE tasks ADD COLUMN locked INTEGER NOT NULL DEFAULT 0 CHECK (locked IN (0, 1));
ALTER TABLE tasks ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0 CHECK (pinned IN (0, 1));

CREATE TABLE IF NOT EXISTS task_early_completion_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    completed_task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    replacement_task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
    completion_scope TEXT NOT NULL CHECK (completion_scope IN ('TASK', 'TOPIC')),
    completion_date TEXT NOT NULL,
    original_planned_date TEXT NOT NULL,
    replacement_from_date TEXT,
    replacement_to_date TEXT,
    selection_reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS topic_resource_preferences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    stage TEXT NOT NULL CHECK (stage IN ('LEARN', 'PRACTICE', 'PYQ')),
    resource_id TEXT REFERENCES study_resources(id) ON DELETE SET NULL,
    provider TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(topic_id, stage)
);

CREATE INDEX IF NOT EXISTS idx_tasks_calendar_search ON tasks(date, topic_id, completed, archived);
CREATE INDEX IF NOT EXISTS idx_tasks_reallocation ON tasks(completed, archived, locked, pinned, date);
CREATE INDEX IF NOT EXISTS idx_early_completion_task ON task_early_completion_history(completed_task_id, created_at);
CREATE INDEX IF NOT EXISTS idx_topic_resource_preferences ON topic_resource_preferences(topic_id, stage);
