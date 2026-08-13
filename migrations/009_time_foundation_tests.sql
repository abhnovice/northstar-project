CREATE TABLE IF NOT EXISTS time_foundation_tests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    test_reference TEXT NOT NULL UNIQUE,
    provider_title TEXT NOT NULL,
    subject TEXT NOT NULL CHECK (subject IN ('QA', 'DI', 'LR', 'VARC')),
    level TEXT NOT NULL DEFAULT 'FOUNDATION',
    category TEXT,
    canonical_topic_group TEXT,
    canonical_topic TEXT,
    cat_priority TEXT NOT NULL DEFAULT 'MEDIUM' CHECK (cat_priority IN ('HIGH', 'MEDIUM', 'LOW')),
    cat_core INTEGER NOT NULL DEFAULT 1 CHECK (cat_core IN (0, 1)),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    imported INTEGER NOT NULL DEFAULT 0 CHECK (imported IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS time_foundation_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    test_id INTEGER NOT NULL REFERENCES time_foundation_tests(id) ON DELETE CASCADE,
    task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
    attempted_on TEXT NOT NULL,
    attempted INTEGER NOT NULL DEFAULT 0 CHECK (attempted >= 0),
    correct INTEGER NOT NULL DEFAULT 0 CHECK (correct >= 0 AND correct <= attempted),
    accuracy REAL NOT NULL DEFAULT 0 CHECK (accuracy >= 0 AND accuracy <= 100),
    time_spent INTEGER NOT NULL DEFAULT 0 CHECK (time_spent >= 0),
    confidence INTEGER NOT NULL DEFAULT 3 CHECK (confidence BETWEEN 1 AND 5),
    notes TEXT NOT NULL DEFAULT '',
    outcome TEXT NOT NULL CHECK (outcome IN ('ADVANCE', 'CONTINUE', 'REPAIR')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE tasks ADD COLUMN time_foundation_test_id INTEGER REFERENCES time_foundation_tests(id);

CREATE INDEX IF NOT EXISTS idx_time_tests_subject_priority
    ON time_foundation_tests(active, cat_core, subject, cat_priority, category);
CREATE INDEX IF NOT EXISTS idx_time_attempts_test_date
    ON time_foundation_attempts(test_id, attempted_on DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_tasks_time_foundation
    ON tasks(time_foundation_test_id, date, archived);

