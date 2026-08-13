ALTER TABLE topics ADD COLUMN progression_level TEXT NOT NULL DEFAULT 'FOUNDATION';
ALTER TABLE topics ADD COLUMN revision_step INTEGER NOT NULL DEFAULT 0;
ALTER TABLE topics ADD COLUMN practice_only INTEGER NOT NULL DEFAULT 0 CHECK (practice_only IN (0, 1));
ALTER TABLE topics ADD COLUMN mastery_score REAL NOT NULL DEFAULT 0;

ALTER TABLE tasks ADD COLUMN topic_id INTEGER REFERENCES topics(id);
ALTER TABLE tasks ADD COLUMN difficulty TEXT NOT NULL DEFAULT 'FOUNDATION';
ALTER TABLE tasks ADD COLUMN adaptive_reason TEXT NOT NULL DEFAULT '';

ALTER TABLE task_resource_assignments ADD COLUMN difficulty TEXT NOT NULL DEFAULT 'FOUNDATION';

ALTER TABLE task_results ADD COLUMN dilr_solved INTEGER CHECK (dilr_solved IN (0, 1));
ALTER TABLE task_results ADD COLUMN dilr_representation TEXT;
ALTER TABLE task_results ADD COLUMN dilr_selectability TEXT;
ALTER TABLE task_results ADD COLUMN varc_error_pattern TEXT;

CREATE TABLE IF NOT EXISTS topic_performance_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    source_type TEXT NOT NULL,
    source_id INTEGER NOT NULL,
    occurred_on TEXT NOT NULL,
    attempted INTEGER NOT NULL DEFAULT 0,
    correct INTEGER NOT NULL DEFAULT 0,
    accuracy REAL NOT NULL DEFAULT 0,
    time_spent INTEGER NOT NULL DEFAULT 0,
    confidence INTEGER NOT NULL DEFAULT 3,
    difficulty TEXT NOT NULL DEFAULT 'FOUNDATION',
    metadata TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(topic_id, source_type, source_id)
);

CREATE TABLE IF NOT EXISTS revision_schedule (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    due_date TEXT NOT NULL,
    interval_index INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'PENDING',
    source_task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
    completed_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS adaptive_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    source_type TEXT NOT NULL,
    source_id INTEGER NOT NULL,
    weight REAL NOT NULL DEFAULT 10,
    reason TEXT NOT NULL DEFAULT '',
    resolved_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(topic_id, source_type, source_id)
);

UPDATE topics SET practice_only=1 WHERE subject='VARC';
UPDATE study_resources
SET difficulty='FOUNDATION',
    platform_path=COALESCE(platform_path, 'CAT Quantitative Aptitude → choose the named topic')
WHERE id='2iim-question-bank';
UPDATE study_resources SET difficulty='FOUNDATION' WHERE id IN ('rodha-cat-free','rodha-dilr-free');
UPDATE study_resources SET difficulty='CAT_LEVEL' WHERE id IN ('varc1000-rc','varc1000-va');

CREATE INDEX IF NOT EXISTS idx_tasks_topic_date ON tasks(topic_id, date);
CREATE INDEX IF NOT EXISTS idx_topic_performance_topic_date ON topic_performance_events(topic_id, occurred_on);
CREATE INDEX IF NOT EXISTS idx_revision_schedule_due ON revision_schedule(status, due_date, topic_id);
CREATE INDEX IF NOT EXISTS idx_adaptive_signals_topic ON adaptive_signals(topic_id, resolved_at);
